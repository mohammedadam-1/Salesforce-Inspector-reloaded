"""UUID v7 generation for time-ordered primary keys.

UUID v7 encodes a Unix timestamp in milliseconds in the most
significant bits, followed by random bits. This provides:
- Time-ordered sorting (B-tree friendly)
- No collisions (random suffix)
- Extractable timestamp
"""

import os
import time
import uuid


def generate_uuid7() -> uuid.UUID:
    """Generate a UUID v7 value.

    Format:
    - 48 bits: Unix timestamp in milliseconds
    - 4 bits: Version (0b0111 = 7)
    - 12 bits: Random
    - 2 bits: Variant (0b10)
    - 62 bits: Random
    """
    timestamp_ms = int(time.time() * 1000)

    random_bytes = os.urandom(10)

    uuid_bytes = bytearray(16)

    uuid_bytes[0] = (timestamp_ms >> 40) & 0xFF
    uuid_bytes[1] = (timestamp_ms >> 32) & 0xFF
    uuid_bytes[2] = (timestamp_ms >> 24) & 0xFF
    uuid_bytes[3] = (timestamp_ms >> 16) & 0xFF
    uuid_bytes[4] = (timestamp_ms >> 8) & 0xFF
    uuid_bytes[5] = timestamp_ms & 0xFF

    uuid_bytes[6] = (uuid_bytes[6] & 0x0F) | 0x70
    uuid_bytes[6] = (uuid_bytes[6] & 0xF0) | (random_bytes[0] >> 4)

    uuid_bytes[8] = (uuid_bytes[8] & 0x3F) | 0x80
    uuid_bytes[8] = (uuid_bytes[8] & 0xC0) | (random_bytes[1] & 0x3F)

    uuid_bytes[9] = random_bytes[2]
    uuid_bytes[10] = random_bytes[3]
    uuid_bytes[11] = random_bytes[4]
    uuid_bytes[12] = random_bytes[5]
    uuid_bytes[13] = random_bytes[6]
    uuid_bytes[14] = random_bytes[7]
    uuid_bytes[15] = random_bytes[8]

    return uuid.UUID(bytes=bytes(uuid_bytes), version=7)
