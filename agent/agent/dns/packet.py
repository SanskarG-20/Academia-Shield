"""
Documented DNS Packet Encoder & Binary Parser.

Parses and constructs RFC 1035 DNS UDP packets using Python struct.
"""

import struct
import socket
from typing import List, Tuple, Optional

# DNS Header Flags & RCODEs
QR_MASK = 0x8000
AA_MASK = 0x0400
TC_MASK = 0x0200
RD_MASK = 0x0100
RA_MASK = 0x0080

RCODE_NOERROR = 0
RCODE_NXDOMAIN = 3

TYPE_A = 1
TYPE_AAAA = 28
CLASS_IN = 1

class DNSQuestion:
    def __init__(self, qname: str, qtype: int = TYPE_A, qclass: int = CLASS_IN):
        self.qname = qname
        self.qtype = qtype
        self.qclass = qclass

    def encode(self) -> bytes:
        data = bytearray()
        for part in self.qname.rstrip(".").split("."):
            data.append(len(part))
            data.extend(part.encode("ascii"))
        data.append(0)  # null domain terminator
        data.extend(struct.pack(">HH", self.qtype, self.qclass))
        return bytes(data)

class DNSResourceRecord:
    def __init__(self, rname: str, rtype: int, rclass: int, ttl: int, rdata: bytes):
        self.rname = rname
        self.rtype = rtype
        self.rclass = rclass
        self.ttl = ttl
        self.rdata = rdata

    def encode(self) -> bytes:
        data = bytearray()
        for part in self.rname.rstrip(".").split("."):
            data.append(len(part))
            data.extend(part.encode("ascii"))
        data.append(0)
        data.extend(struct.pack(">HHIH", self.rtype, self.rclass, self.ttl, len(self.rdata)))
        data.extend(self.rdata)
        return bytes(data)

class DNSPacket:
    """DNS Binary Packet Representation (RFC 1035)."""

    def __init__(self, tx_id: int = 0, flags: int = 0):
        self.tx_id = tx_id
        self.flags = flags
        self.questions: List[DNSQuestion] = []
        self.answers: List[DNSResourceRecord] = []

    @classmethod
    def parse(cls, raw_bytes: bytes) -> "DNSPacket":
        """Parse raw DNS binary packet bytes into DNSPacket instance."""
        if len(raw_bytes) < 12:
            raise ValueError("DNS packet payload under min 12 byte header size")

        tx_id, flags, qdcount, ancount, nscount, arcount = struct.unpack(">HHHHHH", raw_bytes[:12])
        packet = cls(tx_id=tx_id, flags=flags)

        offset = 12
        for _ in range(qdcount):
            qname, offset = cls._parse_domain_name(raw_bytes, offset)
            if offset + 4 > len(raw_bytes):
                break
            qtype, qclass = struct.unpack(">HH", raw_bytes[offset:offset + 4])
            offset += 4
            packet.questions.append(DNSQuestion(qname, qtype, qclass))

        return packet

    @staticmethod
    def _parse_domain_name(data: bytes, offset: int) -> Tuple[str, int]:
        labels = []
        jumped = False
        initial_offset = offset

        while True:
            if offset >= len(data):
                break
            length = data[offset]
            
            # Pointer handling (compression)
            if (length & 0xC0) == 0xC0:
                if offset + 1 >= len(data):
                    break
                pointer_offset = ((length & 0x3F) << 8) | data[offset + 1]
                if not jumped:
                    initial_offset = offset + 2
                    jumped = True
                offset = pointer_offset
                continue

            if length == 0:
                offset += 1
                break

            offset += 1
            if offset + length > len(data):
                break
            labels.append(data[offset:offset + length].decode("ascii", errors="ignore"))
            offset += length

        final_offset = initial_offset if jumped else offset
        return ".".join(labels), final_offset

    def build_nxdomain_response(self) -> bytes:
        """Construct NXDOMAIN (Domain Not Found) binary DNS response."""
        flags = QR_MASK | RD_MASK | RA_MASK | RCODE_NXDOMAIN
        header = struct.pack(">HHHHHH", self.tx_id, flags, len(self.questions), 0, 0, 0)
        body = bytearray(header)
        for q in self.questions:
            body.extend(q.encode())
        return bytes(body)

    def build_blocked_ip_response(self, redirect_ip: str = "127.0.0.1", ttl: int = 60) -> bytes:
        """Construct A-record response mapping domain to local sinkhole IP."""
        flags = QR_MASK | RD_MASK | RA_MASK | RCODE_NOERROR
        an_count = len(self.questions)
        header = struct.pack(">HHHHHH", self.tx_id, flags, len(self.questions), an_count, 0, 0)
        body = bytearray(header)
        for q in self.questions:
            body.extend(q.encode())
            ip_bytes = socket.inet_aton(redirect_ip)
            rr = DNSResourceRecord(q.qname, TYPE_A, CLASS_IN, ttl, ip_bytes)
            body.extend(rr.encode())
        return bytes(body)
