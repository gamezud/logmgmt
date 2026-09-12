"""asyncio syslog listener: UDP and TCP on the same port(s), RFC3164
parsing, and a single writer task draining a bounded queue (see
docs/DECISIONS.md for why — bounded queue + one writer replaces an earlier
per-datagram-task-plus-lock design that had no bound on memory growth).

Binding port 514 needs root / CAP_NET_BIND_SERVICE on Linux. For local
testing without sudo, run with e.g. --udp-port 1514 --tcp-port 1514
(samples/send_syslog.sh defaults to the same 1514).
"""
import argparse
import asyncio
import logging
import os

from ingest.db import connect_async, write_event_async
from ingest.models import NormalizedEvent
from ingest.normalizers import normalize
from ingest.syslog_parser import parse_syslog_line, source_hint_from_fields

log = logging.getLogger("syslog_server")


def handle_message(line: str, tenant: str) -> NormalizedEvent:
    """Pure, synchronous: parsing/normalizing is CPU-bound with no I/O, so
    it runs directly inline in the UDP callback / TCP read loop, and only
    the finished NormalizedEvent goes on the queue.
    """
    try:
        envelope = parse_syslog_line(line)
        source_hint = source_hint_from_fields(envelope.fields)
        payload = envelope
    except ValueError:
        source_hint, payload = "unknown", line
    return normalize(source_hint, payload, tenant)


class SyslogUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, tenant: str, queue: asyncio.Queue):
        self.tenant = tenant
        self.queue = queue

    def datagram_received(self, data: bytes, addr) -> None:
        # A UDP datagram has no line-ending convention of its own (unlike
        # TCP's readline() framing), but senders commonly include a
        # trailing newline anyway (e.g. piping a file through `nc -u`).
        # Strip it so raw_line is consistent between the UDP and TCP paths
        # for the same logical message.
        line = data.decode("utf-8", errors="replace").rstrip("\n")
        event = handle_message(line, self.tenant)
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            # UDP syslog is already best-effort/unordered by definition —
            # datagrams can be lost in transit with no notice to either
            # side — so dropping under listener-side overload matches the
            # transport's own guarantees rather than introducing a new
            # weakness. This callback is synchronous and can't block to
            # wait for space without spawning a task per datagram again,
            # which is exactly what the bounded queue replaces.
            log.warning("UDP queue full (maxsize=%d) — dropping message", self.queue.maxsize)


async def handle_tcp_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    tenant: str,
    queue: asyncio.Queue,
) -> None:
    try:
        while True:
            raw = await reader.readline()  # newline-delimited framing, not RFC6587 octet-counting
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            if not line:
                continue
            event = handle_message(line, tenant)
            # TCP has real flow control: blocking here just leaves bytes in
            # the OS socket buffer, and the sender's own TCP stack slows to
            # match — free, correct backpressure with no drops.
            await queue.put(event)
    finally:
        writer.close()
        await writer.wait_closed()


async def writer_loop(queue: asyncio.Queue, conn) -> None:
    while True:
        event = await queue.get()
        try:
            await write_event_async(conn, event)
        except Exception:
            log.exception("failed to write event, dropping it")
        finally:
            queue.task_done()

def _writer_done(task: asyncio.Task) -> None:
    """writer_loop เป็น infinite loop ที่จัดการ error ของแต่ละรายการเองอยู่แล้ว
    ดังนั้นการที่ callback นี้ถูกเรียกแปลว่า loop ตายทั้งตัว ซึ่งจะทำให้
    server ยังรับ log เข้าคิวต่อไปโดยไม่มีอะไรเขียนลง DB เลย

    ต้องเช็ค task.cancelled() ก่อนเรียก task.exception() เสมอ เพราะการเรียก
    .exception() บน task ที่ถูก cancel จะ re-raise CancelledError ออกมา
    """
    if task.cancelled():
        log.critical("writer_loop was cancelled — no events are being written to the DB anymore")
        return
    exc = task.exception()
    if exc is not None:
        log.critical("writer_loop crashed — no events are being written to the DB anymore", exc_info=exc)
    else:
        log.critical(
            "writer_loop exited its infinite loop with no error — this should never "
            "happen — no events are being written to the DB anymore"
        )

async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Syslog UDP+TCP listener")
    parser.add_argument("--tenant", default=os.environ.get("SYSLOG_TENANT"))
    parser.add_argument("--udp-port", type=int, default=514)
    parser.add_argument("--tcp-port", type=int, default=514)
    parser.add_argument("--queue-size", type=int, default=1000)
    args = parser.parse_args()
    if not args.tenant:
        parser.error("--tenant or SYSLOG_TENANT env var is required")

    conn = await connect_async()
    queue: asyncio.Queue = asyncio.Queue(maxsize=args.queue_size)
    writer_task = asyncio.create_task(writer_loop(queue, conn))
    writer_task.add_done_callback(_writer_done)

    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(
        lambda: SyslogUDPProtocol(args.tenant, queue),
        local_addr=("0.0.0.0", args.udp_port),
    )
    server = await asyncio.start_server(
        lambda r, w: handle_tcp_connection(r, w, args.tenant, queue),
        "0.0.0.0",
        args.tcp_port,
    )
    log.info("listening: UDP %d, TCP %d, tenant=%s", args.udp_port, args.tcp_port, args.tenant)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
