from __future__ import annotations


class ParserError(Exception):
    pass


class FatalParserError(ParserError):
    pass


class MalformedMetadataError(FatalParserError):
    pass


class InvalidMetadataError(ParserError):
    pass


class UnsupportedMetadataTypeError(ParserError):
    pass


class MissingRequiredFieldError(ParserError):
    def __init__(self, metadata_type: str, field: str) -> None:
        super().__init__(f"Missing required field '{field}' for {metadata_type}")
        self.metadata_type = metadata_type
        self.field = field


class ParserVersionMismatchError(FatalParserError):
    pass


class PartialParseWarning(ParserError):
    pass
