"""Read WoW chat messages from addon's in-memory buffer string.

Architecture (Region-Cached Marker Scan):
    The addon stores chat messages in ChatTranslatorHelperDB.wctbuf as a Lua
    string with __WCT_BUF__/__WCT_END__ markers. Lua strings are immutable —
    every RebuildBuffer() creates a NEW string at a NEW address. The old string
    lingers until GC collects it.

    Strategy:
    1. First scan: pymem.pattern_scan_all → find marker address
    2. Cache the memory REGION (via VirtualQueryEx) where the marker lives
    3. On stale marker: scan only the cached region + neighbors (~50-200ms)
    4. Full rescan only if region cache misses

    This avoids the 3-8 second full process scan on every string reallocation.

Safety: Read-only memory access. Warden does not flag external ReadProcessMemory.
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes
import logging
import re
import struct
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Markers written by the addon into ChatTranslatorHelperDB.wctbuf
MARKER_START = b"__WCT_BUF__"
MARKER_END = b"__WCT_END__"

# Polling and retry intervals
POLL_INTERVAL = 0.5  # 500ms between buffer reads
ATTACH_RETRY_INTERVAL = 5.0  # seconds between WoW attach attempts
SCAN_RETRY_INTERVAL = 3.0  # seconds between marker scan attempts
MAX_BUF_READ = 65536  # 64KB max read-ahead for the buffer
RAW_LOG_FILE = "wct_raw.log"  # debug log of all raw AddMessage lines

# Process names to try
WOW_PROCESS_NAMES = ["Wow.exe", "WowT.exe", "WowB.exe"]

# Memory region protection constants
_MEM_COMMIT = 0x1000
_PAGE_READWRITE = 0x04
_PAGE_READONLY = 0x02
_PAGE_EXECUTE_READ = 0x20
_PAGE_EXECUTE_READWRITE = 0x40
_PAGE_WRITECOPY = 0x08
_READABLE_PROTECT = {
    _PAGE_READWRITE, _PAGE_READONLY, _PAGE_EXECUTE_READ,
    _PAGE_EXECUTE_READWRITE, _PAGE_WRITECOPY,
}

# How many neighboring regions to scan when cached region misses
_NEIGHBOR_REGIONS = 4


class _MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.wintypes.DWORD),
        ("Protect", ctypes.wintypes.DWORD),
        ("Type", ctypes.wintypes.DWORD),
    ]


def _extract_max_seq(content: bytes) -> int:
    """Extract the highest sequence number from buffer content."""
    max_seq = 0
    for line in content.split(b"\n"):
        line = line.strip()
        if not line:
            continue
        idx = line.find(b"|")
        if idx <= 0:
            continue
        try:
            seq = int(line[:idx])
            if seq > max_seq:
                max_seq = seq
        except ValueError:
            continue
    return max_seq


def _is_system_noise(text: str) -> bool:
    """Quick check if AddMessage text is obvious system/addon noise."""
    t = re.sub(r"^\d{1,2}:\d{2}:\d{2}\s+", "", text.lstrip())
    if t.startswith(("<DBM>", "<BW>", "<WA>", "|TInterface", "[WCT]", "[MoveAny")):
        return True
    if "|Hachievement:" in t:
        return True
    if "заслужил" in t and "достижение" in t:
        return True
    if "has earned" in t and "achievement" in t:
        return True
    if " создает: " in t or " creates: " in t:
        return True
    if " производит " in t and " в звание " in t:
        return True
    if t.startswith(("Вы превращаете", "You convert")):
        return True
    if t.startswith((
        "Вы не состоите", "You are not in",
        "Смена канала", "Channel ",
        "Вы покинули канал", "You left channel",
        "Ведите себя", "Please keep",
        "Сообщение дня от гильдии", "Guild Message of the Day",
    )):
        return True
    if " ставит маяк " in t or " получает добычу" in t:
        return True
    if " получает предмет" in t or " receives loot" in t:
        return True
    if " засыпает." in t or " очищает " in t or " освобождает " in t:
        return True
    if " находит что-то " in t or " в панике пытается бежать" in t:
        return True
    if t.startswith(("Получено:", "You receive")):
        return True
    return False


class WoWAddonBufReader:
    """Reads chat messages from the WoW addon's in-memory buffer string.

    Uses region-cached marker scanning: after finding the marker once,
    caches the memory region. On stale marker, rescans only the cached
    region and neighbors (~50-200ms instead of 3-8s full scan).
    """

    def __init__(self, on_new_line: Callable[[str], None]) -> None:
        self._on_new_line = on_new_line
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pm = None  # pymem.Pymem instance
        self._attached = False
        self._last_seq = 0

        # Current marker address and its region
        self._buf_addr: int = 0
        self._cached_region: tuple[int, int] | None = None  # (base, size)
        self._all_regions: list[tuple[int, int]] = []  # sorted by base addr
        self._cached_region_index: int = -1  # index in _all_regions

        # Track consecutive stale reads to trigger rescan
        self._stale_count: int = 0

        # Periodic rescan: check if a newer buffer exists every N seconds.
        # This catches "frozen" old Lua strings that are still readable
        # but no longer updated (a newer string exists elsewhere).
        self._last_rescan: float = 0.0
        self._rescan_interval: float = 3.0  # seconds between region rescans
        self._same_addr_count: int = 0  # consecutive rescans finding same addr

    @property
    def is_attached(self) -> bool:
        return self._attached

    def start(self) -> None:
        """Start the addon buffer reader polling thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Addon buffer reader thread started")

    def stop(self) -> None:
        """Stop the reader."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        self._detach()
        logger.info("Addon buffer reader stopped")

    def _run_loop(self) -> None:
        """Main loop: attach → find marker → poll → rescan on stale."""
        while not self._stop_event.is_set():
            # Step 1: attach to WoW process
            if not self._attached:
                try:
                    self._attach()
                except Exception as e:
                    logger.info("Cannot attach to WoW: %s", e)
                    self._stop_event.wait(ATTACH_RETRY_INTERVAL)
                    continue

            # Step 2: find marker if we don't have one
            if self._buf_addr == 0:
                try:
                    found = self._find_marker()
                except Exception as e:
                    logger.warning("Marker scan error: %s", e)
                    if not self._is_process_alive():
                        logger.info("WoW process gone, detaching")
                        self._detach()
                    self._stop_event.wait(SCAN_RETRY_INTERVAL)
                    continue

                if not found:
                    self._stop_event.wait(SCAN_RETRY_INTERVAL)
                    continue

            # Step 3: read buffer and deliver messages
            try:
                self._poll_buffer()
            except Exception as e:
                logger.warning("Buffer read error: %s", e)
                if not self._is_process_alive():
                    logger.info("WoW process gone, detaching")
                    self._detach()
                    continue

            self._stop_event.wait(POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Process attach/detach
    # ------------------------------------------------------------------

    def _attach(self) -> None:
        """Attach to WoW process via pymem."""
        import pymem
        import pymem.exception

        for proc_name in WOW_PROCESS_NAMES:
            try:
                self._pm = pymem.Pymem(proc_name)
                logger.info(
                    "Attached to %s (PID %d)",
                    proc_name, self._pm.process_id,
                )
                self._attached = True
                # Cache memory regions for fast rescans
                self._all_regions = self._get_memory_regions()
                logger.info("Cached %d readable memory regions", len(self._all_regions))
                return
            except pymem.exception.ProcessNotFound:
                continue

        raise RuntimeError("WoW process not found")

    def _detach(self) -> None:
        """Detach from WoW process."""
        if self._pm:
            with contextlib.suppress(Exception):
                self._pm.close_process()
        self._pm = None
        self._attached = False
        self._buf_addr = 0
        self._cached_region = None
        self._cached_region_index = -1
        self._all_regions = []
        self._stale_count = 0

    def _is_process_alive(self) -> bool:
        """Check if the WoW process is still accessible."""
        if not self._pm:
            return False
        try:
            self._pm.read_bytes(self._pm.base_address, 1)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Memory region enumeration
    # ------------------------------------------------------------------

    def _get_memory_regions(self) -> list[tuple[int, int]]:
        """Get readable memory regions of WoW process via VirtualQueryEx.

        Returns list of (base_address, region_size) sorted by base address.
        """
        if not self._pm:
            return []

        regions: list[tuple[int, int]] = []
        kernel32 = ctypes.windll.kernel32
        mbi = _MEMORY_BASIC_INFORMATION()
        address = 0
        max_address = 0x7FFFFFFFFFFF

        while address < max_address:
            result = kernel32.VirtualQueryEx(
                self._pm.process_handle,
                ctypes.c_void_p(address),
                ctypes.byref(mbi),
                ctypes.sizeof(mbi),
            )
            if result == 0:
                break

            if (
                mbi.State == _MEM_COMMIT
                and mbi.Protect in _READABLE_PROTECT
                and 0 < mbi.RegionSize <= 100 * 1024 * 1024
            ):
                regions.append((address, mbi.RegionSize))

            address += mbi.RegionSize
            if mbi.RegionSize == 0:
                address += 0x1000

        regions.sort(key=lambda r: r[0])
        return regions

    def _find_region_for_addr(self, addr: int) -> tuple[int, int, int] | None:
        """Find which cached region contains the given address.

        Returns (region_base, region_size, index_in_all_regions) or None.
        """
        for i, (base, size) in enumerate(self._all_regions):
            if base <= addr < base + size:
                return base, size, i
        return None

    # ------------------------------------------------------------------
    # Marker scanning (region-cached)
    # ------------------------------------------------------------------

    def _find_marker(self, min_seq: int = 0) -> bool:
        """Find the __WCT_BUF__ marker, using region cache if available.

        Args:
            min_seq: only accept markers with max_seq > min_seq.
                     Used after frozen detection to skip the old, stale string.

        Strategy:
        1. If we have a cached region, scan it + neighbors first (~50-200ms)
        2. If not found, do a full scan via pymem (~3-8s)
        3. Cache the region where we found the marker
        """
        if not self._pm:
            return False

        # Try cached region first (fast path)
        if self._cached_region is not None:
            t0 = time.monotonic()
            addr = self._scan_region_neighborhood(min_seq=min_seq)
            elapsed = time.monotonic() - t0

            if addr:
                logger.info(
                    "Region cache HIT: marker at 0x%X (%.0fms)",
                    addr, elapsed * 1000,
                )
                self._buf_addr = addr
                self._stale_count = 0
                return True

            logger.info(
                "Region cache MISS (%.0fms), refreshing regions and doing full scan",
                elapsed * 1000,
            )
            # Refresh region cache (process may have allocated new regions)
            self._all_regions = self._get_memory_regions()
            logger.info("Refreshed to %d readable memory regions", len(self._all_regions))

        # Full scan (slow path)
        t0 = time.monotonic()
        addr = self._full_marker_scan(min_seq=min_seq)
        elapsed = time.monotonic() - t0

        if addr:
            logger.info(
                "Full scan: marker at 0x%X (%.1fs)",
                addr, elapsed,
            )
            # Cache the region
            region_info = self._find_region_for_addr(addr)
            if region_info:
                base, size, idx = region_info
                self._cached_region = (base, size)
                self._cached_region_index = idx
                logger.info(
                    "Cached region: 0x%X - 0x%X (%d KB)",
                    base, base + size, size // 1024,
                )

            self._buf_addr = addr
            self._stale_count = 0

            # Skip existing buffer history on first connect
            if self._last_seq == 0:
                try:
                    raw = self._pm.read_bytes(addr, MAX_BUF_READ)
                    if raw.startswith(MARKER_START):
                        end_idx = raw.find(MARKER_END, len(MARKER_START))
                        if end_idx != -1:
                            content = raw[len(MARKER_START):end_idx]
                            max_seq = _extract_max_seq(content)
                            if max_seq > 0:
                                self._last_seq = max_seq
                                logger.info("Skipping existing buffer (last_seq=%d)", max_seq)
                except Exception:
                    pass

            return True

        logger.warning("Full scan: marker not found")
        return False

    def _scan_region_neighborhood(self, min_seq: int = 0) -> int:
        """Scan cached region + neighbors for the marker.

        Args:
            min_seq: only accept markers with max_seq > min_seq.

        Returns marker address or 0.
        """
        if not self._pm or self._cached_region_index < 0:
            return 0

        pattern = re.compile(re.escape(MARKER_START))

        # Build list of regions to scan: cached + neighbors
        scan_start = max(0, self._cached_region_index - _NEIGHBOR_REGIONS)
        scan_end = min(len(self._all_regions), self._cached_region_index + _NEIGHBOR_REGIONS + 1)

        best_addr = 0
        best_seq = -1
        total_scanned = 0

        for i in range(scan_start, scan_end):
            base, size = self._all_regions[i]
            total_scanned += size
            try:
                raw = self._pm.read_bytes(base, size)
            except Exception:
                continue

            for match in pattern.finditer(raw):
                abs_addr = base + match.start()
                content_start = match.start()
                remaining = len(raw) - content_start
                chunk = raw[content_start:content_start + min(remaining, MAX_BUF_READ)]

                if not chunk.startswith(MARKER_START):
                    continue
                marker_end = chunk.find(MARKER_END, len(MARKER_START))
                if marker_end == -1:
                    continue

                content = chunk[len(MARKER_START):marker_end]
                max_seq = _extract_max_seq(content)
                if max_seq > best_seq and max_seq > min_seq:
                    best_seq = max_seq
                    best_addr = abs_addr

        if best_addr:
            # Update cached region to where we actually found it
            region_info = self._find_region_for_addr(best_addr)
            if region_info:
                base, size, idx = region_info
                self._cached_region = (base, size)
                self._cached_region_index = idx

        logger.debug(
            "Region scan: checked %d regions (%d KB), best_seq=%d",
            scan_end - scan_start, total_scanned // 1024, best_seq,
        )
        return best_addr

    def _full_marker_scan(self, min_seq: int = 0) -> int:
        """Full process scan for the marker via pymem.

        Args:
            min_seq: only accept markers with max_seq > min_seq.

        Returns the address of the best (highest seq) marker, or 0.
        """
        if not self._pm:
            return 0

        logger.info("Full scan: searching for addon buffer marker...")

        import pymem.pattern
        try:
            addrs = pymem.pattern.pattern_scan_all(
                self._pm.process_handle,
                re.escape(MARKER_START),
                return_multiple=True,
            )
        except Exception as e:
            logger.warning("pattern_scan_all failed: %s", e)
            return 0

        if not addrs:
            return 0

        logger.info("Full scan: found %d raw matches", len(addrs))

        best_addr = 0
        best_seq = -1
        for a in addrs:
            try:
                raw = self._pm.read_bytes(a, MAX_BUF_READ)
            except Exception:
                continue
            if not raw.startswith(MARKER_START):
                continue
            end_idx = raw.find(MARKER_END, len(MARKER_START))
            if end_idx == -1:
                continue
            content = raw[len(MARKER_START):end_idx]
            max_seq = _extract_max_seq(content)
            if max_seq > best_seq and max_seq > min_seq:
                best_seq = max_seq
                best_addr = a

        if best_addr:
            logger.info(
                "Full scan: best marker at 0x%X (max_seq=%d, %d candidates)",
                best_addr, best_seq, len(addrs),
            )
        return best_addr

    def _check_for_newer_buffer(self) -> None:
        """Check if a newer buffer exists (new Lua string from RebuildBuffer).

        Strategy escalation:
        - First 2 checks: neighborhood scan (fast, ~15ms, ±4 regions)
        - After 2 same-addr: heap scan (broader, ~1-3s, all ≤8MB regions)
        - After heap scan: refresh region list + heap scan
        """
        if not self._pm or not self._all_regions:
            return

        t0 = time.monotonic()

        if self._same_addr_count < 2:
            # Fast: neighborhood only
            new_addr = self._scan_region_neighborhood(min_seq=0)
            scan_type = "neighborhood"
        else:
            # Broader: all heap regions (≤8MB each)
            if self._same_addr_count == 2:
                # Refresh region list — new allocations may have appeared
                self._all_regions = self._get_memory_regions()
            new_addr = self._scan_heap_regions()
            scan_type = "heap"

        elapsed = time.monotonic() - t0

        if new_addr and new_addr != self._buf_addr:
            logger.info(
                "Found newer buffer at 0x%X (was 0x%X), %s scan took %.0fms",
                new_addr, self._buf_addr, scan_type, elapsed * 1000,
            )
            self._buf_addr = new_addr
            self._stale_count = 0
            self._same_addr_count = 0
            # Update cached region
            region_info = self._find_region_for_addr(new_addr)
            if region_info:
                base, size, idx = region_info
                self._cached_region = (base, size)
                self._cached_region_index = idx
        else:
            self._same_addr_count += 1
            if self._same_addr_count <= 3 or self._same_addr_count % 10 == 0:
                logger.info(
                    "Periodic rescan #%d: same buffer (%s, %.0fms)",
                    self._same_addr_count, scan_type, elapsed * 1000,
                )

    def _scan_heap_regions(self) -> int:
        """Scan likely Lua heap regions for the best (highest seq) marker.

        Lua allocates strings in PAGE_READWRITE regions, typically 1-4MB.
        We scan only regions ≤ 8MB to avoid image/resource regions.
        With ~4700 total regions, maybe ~500 are ≤8MB RW, totaling ~500MB.
        This is ~4-8x faster than pymem's full scan of all memory.

        Returns marker address or 0.
        """
        if not self._pm:
            return 0

        pattern = re.compile(re.escape(MARKER_START))
        best_addr = 0
        best_seq = -1
        regions_scanned = 0
        bytes_scanned = 0

        for base, size in self._all_regions:
            # Skip large regions — Lua heap chunks are typically ≤ 4MB
            if size > 8 * 1024 * 1024:
                continue
            regions_scanned += 1
            bytes_scanned += size
            try:
                raw = self._pm.read_bytes(base, size)
            except Exception:
                continue

            for match in pattern.finditer(raw):
                content_start = match.start()
                remaining = len(raw) - content_start
                chunk = raw[content_start:content_start + min(remaining, MAX_BUF_READ)]

                if not chunk.startswith(MARKER_START):
                    continue
                marker_end = chunk.find(MARKER_END, len(MARKER_START))
                if marker_end == -1:
                    continue

                content = chunk[len(MARKER_START):marker_end]
                max_seq = _extract_max_seq(content)
                if max_seq > best_seq:
                    best_seq = max_seq
                    best_addr = base + match.start()

        logger.debug(
            "Heap scan: %d regions, %d MB, best_seq=%d",
            regions_scanned, bytes_scanned // (1024 * 1024), best_seq,
        )
        return best_addr

    # ------------------------------------------------------------------
    # Buffer reading and polling
    # ------------------------------------------------------------------

    def _read_buffer(self) -> str | None:
        """Read buffer content at the current marker address."""
        if not self._pm or self._buf_addr == 0:
            return None
        try:
            raw = self._pm.read_bytes(self._buf_addr, MAX_BUF_READ)
        except Exception:
            return None

        if not raw.startswith(MARKER_START):
            return None

        end_idx = raw.find(MARKER_END, len(MARKER_START))
        if end_idx == -1:
            return None

        content_bytes = raw[len(MARKER_START):end_idx]
        try:
            return content_bytes.decode("utf-8", errors="replace")
        except Exception:
            return None

    def _poll_buffer(self) -> None:
        """Read the addon buffer and deliver new messages.

        Handles two staleness scenarios:
        1. Marker gone (read returns None) — string was GC'd → immediate rescan
        2. Frozen buffer — old Lua string still readable but outdated.
           We do periodic region rescans (every 3s) to check if a newer
           buffer with higher seq exists elsewhere in memory.
        """
        if not self._pm or self._buf_addr == 0:
            return

        content = self._read_buffer()
        if content is None:
            # Marker stale — string was GC'd or memory changed
            self._stale_count += 1
            if self._stale_count >= 2:
                logger.info(
                    "Marker gone (count=%d), triggering rescan",
                    self._stale_count,
                )
                self._buf_addr = 0
                self._stale_count = 0
            return

        stripped = content.strip()
        if not stripped:
            return

        self._stale_count = 0
        self._deliver_new_messages(content)

        # Periodic rescan: check if a newer buffer exists.
        # Old Lua strings stay readable after RebuildBuffer() — they're
        # immutable, just waiting for GC. The new string (with higher seq)
        # lives at a different address. We do a cheap region scan to find it.
        now = time.monotonic()
        if now - self._last_rescan >= self._rescan_interval:
            self._last_rescan = now
            self._check_for_newer_buffer()

    def _deliver_new_messages(self, content: str) -> None:
        """Parse buffer content and deliver messages with seq > last_seq."""
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        if not lines:
            return

        # Detect seq reset: after /reload, addon restarts seq from 1
        max_seq_in_buf = 0
        for line in lines:
            parts = line.split("|", 1)
            if parts:
                try:
                    s = int(parts[0])
                    if s > max_seq_in_buf:
                        max_seq_in_buf = s
                except ValueError:
                    pass

        if max_seq_in_buf > 0 and max_seq_in_buf < self._last_seq:
            logger.info(
                "Seq reset detected (buf max=%d, last_seq=%d) — resetting tracker",
                max_seq_in_buf, self._last_seq,
            )
            self._last_seq = 0

        new_count = 0
        for line in lines:
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue

            try:
                seq = int(parts[0])
            except ValueError:
                continue

            if seq <= self._last_seq:
                continue

            self._last_seq = seq
            new_count += 1

            kind = parts[1]
            payload = parts[2]

            if kind == "RAW":
                # Log ALL raw messages to file for debugging
                try:
                    with open(RAW_LOG_FILE, "a", encoding="utf-8") as f:
                        t = time.localtime()
                        ts = f"{t.tm_mon}/{t.tm_mday} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}.000"
                        f.write(f"[{ts}] #{seq} {payload}\n")
                except OSError:
                    pass

                if _is_system_noise(payload):
                    logger.debug("Addon raw #%d: [skip system] %s", seq, payload[:120])
                    continue

                # Strip embedded WoW chat timestamp (HH:MM:SS)
                stripped_payload = re.sub(r"^\d{1,2}:\d{2}:\d{2}\s+", "", payload)

                t = time.localtime()
                ts = f"{t.tm_mon}/{t.tm_mday} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}.000"
                log_line = f"{ts}  {stripped_payload}"
                logger.info("Addon raw #%d: %s", seq, log_line[:200])
                self._on_new_line(log_line)
            else:
                # Legacy format: SEQ|CHANNEL|Author|Text
                legacy_parts = line.split("|", 3)
                if len(legacy_parts) >= 4:
                    channel = legacy_parts[1]
                    author = legacy_parts[2]
                    text = legacy_parts[3]
                    log_line = self._make_synthetic_log_line(channel, author, text)
                    if log_line:
                        logger.debug("Addon msg #%d: %s", seq, log_line[:80])
                        self._on_new_line(log_line)

        if new_count > 0:
            logger.info("Delivered %d new messages (last_seq=%d)", new_count, self._last_seq)

    @staticmethod
    def _make_synthetic_log_line(channel: str, author: str, text: str) -> str | None:
        """Convert addon buffer entry to a WoW chat log line for parse_line()."""
        _ADDON_CHANNEL_TO_LOG = {
            "SAY": "Say",
            "YELL": "Yell",
            "PARTY": "Party",
            "PARTY_LEADER": "Party Leader",
            "RAID": "Raid",
            "RAID_LEADER": "Raid Leader",
            "RAID_WARNING": "Raid Warning",
            "GUILD": "Guild",
            "OFFICER": "Officer",
            "INSTANCE_CHAT": "Instance",
            "INSTANCE_CHAT_LEADER": "Instance Leader",
        }
        t = time.localtime()
        ts = f"{t.tm_mon}/{t.tm_mday} {t.tm_hour:02d}:{t.tm_min:02d}:{t.tm_sec:02d}.000"

        if channel == "WHISPER":
            return f"{ts}  [{author}] whispers: {text}"
        if channel == "WHISPER_INFORM":
            return f"{ts}  To [{author}]: {text}"

        log_channel = _ADDON_CHANNEL_TO_LOG.get(channel)
        if log_channel is None:
            return None

        return f"{ts}  [{log_channel}] {author}: {text}"


class MemoryChatWatcher:
    """High-level watcher: bridges WoWAddonBufReader to the pipeline."""

    def __init__(self, on_new_line: Callable[[str], None]) -> None:
        self._on_new_line = on_new_line
        self._reader = WoWAddonBufReader(on_new_line=on_new_line)

    def start(self) -> None:
        self._reader.start()

    def stop(self) -> None:
        self._reader.stop()

    @property
    def is_attached(self) -> bool:
        return self._reader.is_attached
