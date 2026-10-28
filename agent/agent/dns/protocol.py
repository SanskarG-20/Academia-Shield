"""
Documented Binary DNS Packet Encoder & Parser (RFC 1035).

Handles DNS header parsing, QNAME decoding with IDNA punycode normalization,
transaction ID preservation, malformed packet rejection, and response building.
"""

import struct
import socket
import logging
from typing import List, Tuple, Optional

LOGGER = logging.getLogger(__name__)

# DNS Flags & RCODEs
QR_RESPONSE = 0x8000
AA_AUTHORITATIVE = 0x0400
TC_TRUNCATED = 0x0200
RD_RECURSION_DESIRED = 0x0100
RA_RECURSION_AVAILABLE = 0x0080

RCODE_NOERROR = 0
RCODE_FORMERR = 1
RCODE_SERVFAIL = 2
RCODE_NXDOMAIN = 3
RCODE_NOTIMP = 4

TYPE_A = 1
TYPE_NS = 2
TYPE_CNAME = 5
TYPE_PTR = 12
TYPE_MX = 15
TYPE_TXT = 16
TYPE_AAAA = 28
TYPE_ANY = 255

CLASS_IN = 1

def normalize_domain_name(name: str) -> str:
    """
    Normalize domain name: lowercase, strip trailing dots, and encode/decode IDNA punycode.
    """
    if not name:
        return ""
    clean = name.strip().lower().rstrip(".")
    if not clean:
        return ""
    try:
        # IDNA Punycode normalization
        return clean.encode("idna").decode("ascii")
    except Exception:
        return clean

class DNSQuestion:
    """DNS Question Section Representation."""

    def __init__(self, qname: str, qtype: int = TYPE_A, qclass: int = CLASS_IN):
        self.qname = normalize_domain_name(qname)
        self.qtype = qtype
        self.qclass = qclass

    def encode(self) -> bytes:
        data = bytearray()
        if self.qname:
            for part in self.qname.split("."):
                part_bytes = part.encode("ascii", errors="ignore")
                data.append(len(part_bytes))
                data.extend(part_bytes)
        data.append(0)  # Null terminator
        data.extend(struct.pack(">HH", self.qtype, self.qclass))
        return bytes(data)

class DNSResourceRecord:
    """DNS Resource Record (Answer/Authority/Additional)."""

    def __init__(self, rname: str, rtype: int, rclass: int, ttl: int, rdata: bytes):
        self.rname = normalize_domain_name(rname)
        self.rtype = rtype
        self.rclass = rclass
        self.ttl = ttl
        self.rdata = rdata

    def encode(self) -> bytes:
        data = bytearray()
        if self.rname:
            for part in self.rname.split("."):
                part_bytes = part.encode("ascii", errors="ignore")
                data.append(len(part_bytes))
                data.extend(part_bytes)
        data.append(0)
        data.extend(struct.pack(">HHIH", self.rtype, self.rclass, self.ttl, len(self.rdata)))
        data.extend(self.rdata)
        return bytes(data)

class DNSPacket:
    """Full DNS Binary Packet Parser & Builder."""

    def __init__(self, tx_id: int = 0, flags: int = 0):
        self.tx_id = tx_id
        self.flags = flags
        self.questions: List[DNSQuestion] = []
        self.answers: List[DNSResourceRecord] = []
        self.authorities: List[DNSResourceRecord] = []
        self.additionals: List[DNSResourceRecord] = []

    @classmethod
    def parse(cls, raw_bytes: bytes) -> "DNSPacket":
        """
        Parse raw DNS binary payload into DNSPacket instance.
        Validates min length, header fields, and malformed structures.
        """
        if not raw_bytes or len(raw_bytes) < 12:
            raise ValueError("Malformed packet: Payload smaller than 12-byte DNS header")

        tx_id, flags, qdcount, ancount, nscount, arcount = struct.unpack(">HHHHHH", raw_bytes[:12])
        packet = cls(tx_id=tx_id, flags=flags)

        offset = 12
        # Parse Question Section
        for _ in range(qdcount):
            if offset >= len(raw_bytes):
                raise ValueError("Malformed packet: Truncated question section")
            qname, offset = cls._parse_domain_name(raw_bytes, offset)
            if offset + 4 > len(raw_bytes):
                raise ValueError("Malformed packet: Truncated QTYPE/QCLASS")
            qtype, qclass = struct.unpack(">HH", raw_bytes[offset:offset + 4])
            offset += 4
            packet.questions.append(DNSQuestion(qname, qtype, qclass))

        return packet

    @staticmethod
    def _parse_domain_name(data: bytes, offset: int) -> Tuple[str, int]:
        labels = []
        jumped = False
        initial_offset = offset
        visited_offsets = set()

        while True:
            if offset >= len(data):
                raise ValueError("Malformed packet: Out of bounds domain label reading")
            
            if offset in visited_offsets:
                raise ValueError("Malformed packet: Pointer loop detected in domain labels")
            visited_offsets.add(offset)

            length = data[offset]

            # Check for compression pointer (top 2 bits set)
            if (length & 0xC0) == 0xC0:
                if offset + 1 >= len(data):
                    raise ValueError("Malformed packet: Truncated compression pointer")
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
                raise ValueError("Malformed packet: Label length extends past packet end")

            label = data[offset:offset + length].decode("ascii", errors="ignore")
            labels.append(label)
            offset += length

        final_offset = initial_offset if jumped else offset
        full_name = ".".join(labels)
        return normalize_domain_name(full_name), final_offset

    def build_nxdomain_response(self) -> bytes:
        """Construct RFC 1035 compliant NXDOMAIN response while preserving client transaction ID."""
        flags = QR_RESPONSE | RD_RECURSION_DESIRED | RA_RECURSION_AVAILABLE | RCODE_NXDOMAIN
        header = struct.pack(">HHHHHH", self.tx_id, flags, len(self.questions), 0, 0, 0)
        body = bytearray(header)
        for q in self.questions:
            body.extend(q.encode())
        return bytes(body)

    def build_servfail_response(self) -> bytes:
        """Construct SERVFAIL response when upstream resolution fails."""
        flags = QR_RESPONSE | RD_RECURSION_DESIRED | RA_RECURSION_AVAILABLE | RCODE_SERVFAIL
        header = struct.pack(">HHHHHH", self.tx_id, flags, len(self.questions), 0, 0, 0)
        body = bytearray(header)
        for q in self.questions:
            body.extend(q.encode())
        return bytes(body)

    def build_a_record_response(self, redirect_ip: str = "127.0.0.1", ttl: int = 60) -> bytes:
        """Construct A-record response mapping domain to loopback IP."""
        flags = QR_RESPONSE | RD_RECURSION_DESIRED | RA_RECURSION_AVAILABLE | RCODE_NOERROR
        an_count = len(self.questions)
        header = struct.pack(">HHHHHH", self.tx_id, flags, len(self.questions), an_count, 0, 0)
        body = bytearray(header)
        for q in self.questions:
            body.extend(q.encode())
            ip_bytes = socket.inet_aton(redirect_ip)
            rr = DNSResourceRecord(q.qname, TYPE_A, CLASS_IN, ttl, ip_bytes)
            body.extend(rr.encode())
        return bytes(body)
