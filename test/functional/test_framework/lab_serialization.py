"""Token-aware decoding for lab tests using txnotokens=0."""

import struct

from test_framework.messages import (
    CBlock,
    CBlockHeader,
    CTransaction,
    CTxIn,
    CTxInWitness,
    CTxOut,
    CTxWitness,
    deser_vector,
)


def read_token_id(stream):
    # Bitcoin VARINT encoding, distinct from CompactSize.
    value = 0
    for _ in range(5):
        raw = stream.read(1)
        if len(raw) != 1:
            raise ValueError("Truncated token identifier")
        byte = raw[0]
        value = (value << 7) | (byte & 0x7f)
        if byte & 0x80:
            value += 1
        else:
            if value > 0xffffffff:
                raise ValueError("Token identifier exceeds uint32")
            return value
    raise ValueError("Token identifier is too long")


def write_token_id(value):
    if not 0 <= value <= 0xffffffff:
        raise ValueError("Token identifier exceeds uint32")
    encoded = bytearray()
    while True:
        encoded.append((value & 0x7f) | (0x80 if encoded else 0))
        if value <= 0x7f:
            break
        value = (value >> 7) - 1
    return bytes(reversed(encoded))


class TokenAwareOutput(CTxOut):
    __slots__ = ("nTokenId",)

    def __init__(self, nValue=0, scriptPubKey=b"", nTokenId=0):
        super().__init__(nValue, scriptPubKey)
        self.nTokenId = nTokenId

    def deserialize(self, stream):
        super().deserialize(stream)
        self.nTokenId = read_token_id(stream)

    def serialize(self):
        return super().serialize() + write_token_id(self.nTokenId)


class TokenAwareTransaction(CTransaction):
    def deserialize(self, stream):
        self.nVersion = struct.unpack("<i", stream.read(4))[0]
        output_type = TokenAwareOutput if self.nVersion >= 4 else CTxOut
        self.vin = deser_vector(stream, CTxIn)
        self.vout = []
        flags = 0

        if not self.vin:
            flags = struct.unpack("<B", stream.read(1))[0]
            if flags:
                self.vin = deser_vector(stream, CTxIn)
                self.vout = deser_vector(stream, output_type)
        else:
            self.vout = deser_vector(stream, output_type)

        self.wit = CTxWitness()
        if flags & 1:
            self.wit.vtxinwit = [CTxInWitness() for _ in self.vin]
            self.wit.deserialize(stream)
            if self.wit.is_null():
                raise ValueError("Superfluous witness record")
            flags ^= 1
        if flags:
            raise ValueError("Unknown transaction optional data")

        self.nLockTime = struct.unpack("<I", stream.read(4))[0]
        self.sha256 = None
        self.hash = None


class TokenAwareBlock(CBlock):
    def deserialize(self, stream):
        CBlockHeader.deserialize(self, stream)
        self.vtx = deser_vector(stream, TokenAwareTransaction)
