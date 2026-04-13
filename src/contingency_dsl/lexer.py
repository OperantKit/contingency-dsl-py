"""Lexer for contingency-dsl: text -> token stream.

Handles the FR5 compact notation by splitting schedule type prefix
from the following numeric value.
"""

from __future__ import annotations

from .enums import (
    COMBINATOR_KEYWORDS,
    DR_KEYWORDS,
    LOWERCASE_RESERVED,
    SCHEDULE_TYPE_KEYWORDS,
    SPECIAL_KEYWORDS,
)
from .errors import LexError, SourceSpan
from .tokens import Token, TokenType


def tokenize(source: str) -> list[Token]:
    """Tokenize DSL source text into a list of tokens."""
    tokens: list[Token] = []
    lines = source.split("\n")

    for line_num, line_text in enumerate(lines, start=1):
        col = 0
        while col < len(line_text):
            ch = line_text[col]

            # Skip whitespace
            if ch in (" ", "\t"):
                col += 1
                continue

            # Line comment
            if ch == "-" and col + 1 < len(line_text) and line_text[col + 1] == "-":
                break  # skip rest of line

            # Punctuation
            if ch == "(":
                tokens.append(Token(TokenType.LPAREN, "(", line_num, col + 1))
                col += 1
                continue
            if ch == ")":
                tokens.append(Token(TokenType.RPAREN, ")", line_num, col + 1))
                col += 1
                continue
            if ch == ",":
                tokens.append(Token(TokenType.COMMA, ",", line_num, col + 1))
                col += 1
                continue
            if ch == "=":
                tokens.append(Token(TokenType.EQUALS, "=", line_num, col + 1))
                col += 1
                continue
            if ch == "@":
                tokens.append(Token(TokenType.AT, "@", line_num, col + 1))
                col += 1
                continue

            # String literal: "..."
            if ch == '"':
                start_col = col
                col += 1  # skip opening quote
                string_chars: list[str] = []
                while col < len(line_text) and line_text[col] != '"':
                    string_chars.append(line_text[col])
                    col += 1
                if col >= len(line_text):
                    raise LexError(
                        "unterminated string literal",
                        SourceSpan(line_num, start_col + 1),
                    )
                col += 1  # skip closing quote
                tokens.append(
                    Token(TokenType.STRING_LITERAL, "".join(string_chars), line_num, start_col + 1)
                )
                continue

            # Number (starts with digit or decimal point)
            if ch.isdigit() or (ch == "." and col + 1 < len(line_text) and line_text[col + 1].isdigit()):
                start_col = col
                num_str = ""
                while col < len(line_text) and (line_text[col].isdigit() or line_text[col] == "."):
                    num_str += line_text[col]
                    col += 1
                tokens.append(Token(TokenType.NUMBER, num_str, line_num, start_col + 1))
                # Check for immediately following time unit
                remaining = line_text[col:]
                if remaining.startswith("min"):
                    tokens.append(Token(TokenType.TIME_UNIT, "min", line_num, col + 1))
                    col += 3
                elif remaining.startswith("ms"):
                    tokens.append(Token(TokenType.TIME_UNIT, "ms", line_num, col + 1))
                    col += 2
                elif remaining.startswith("s") and (col + 1 >= len(line_text) or not line_text[col + 1].isalpha()):
                    tokens.append(Token(TokenType.TIME_UNIT, "s", line_num, col + 1))
                    col += 1
                continue

            # Alphabetic word
            if ch.isalpha() or ch == "_":
                start_col = col
                word = ""
                while col < len(line_text) and (line_text[col].isalnum() or line_text[col] == "_"):
                    word += line_text[col]
                    col += 1

                token = _classify_word(word, line_num, start_col + 1)
                if token is not None:
                    tokens.append(token)
                    # If schedule type, check for immediately following number
                    if token.type == TokenType.SCHEDULE_TYPE:
                        keyword = word[:2]
                        rest = word[2:]
                        if rest:
                            tokens[-1] = Token(TokenType.SCHEDULE_TYPE, keyword, line_num, start_col + 1)
                            # Check for decimal continuation: FR5.0 -> word="FR5", then "." in source
                            decimal_extra = ""
                            if col < len(line_text) and line_text[col] == ".":
                                dc = col + 1
                                while dc < len(line_text) and line_text[dc].isdigit():
                                    dc += 1
                                if dc > col + 1:  # found digits after "."
                                    decimal_extra = line_text[col:dc]
                                    col = dc
                            _lex_number_suffix(rest + decimal_extra, tokens, line_num, start_col + 3)
                    elif token.type == TokenType.DR_MOD:
                        keyword = word[:3]
                        rest = word[3:]
                        if rest:
                            tokens[-1] = Token(TokenType.DR_MOD, keyword, line_num, start_col + 1)
                            _lex_number_suffix(rest, tokens, line_num, start_col + 4)
                    elif token.type == TokenType.LH:
                        # LH/LimitedHold followed by digits: LH10 -> LH + 10, LimitedHold10 -> LH + 10
                        prefix_len = 11 if word.startswith("LimitedHold") else 2
                        rest = word[prefix_len:]
                        if rest:
                            tokens[-1] = Token(TokenType.LH, word[:prefix_len], line_num, start_col + 1)
                            _lex_number_suffix(rest, tokens, line_num, start_col + prefix_len + 1)
                    continue
                # Should not reach here (all alpha words are classified)
                raise LexError(
                    f"unexpected word: '{word}'",
                    SourceSpan(line_num, start_col + 1, len(word)),
                )

            # Unknown character
            raise LexError(
                f"unexpected character: '{ch}'",
                SourceSpan(line_num, col + 1),
            )

    tokens.append(Token(TokenType.EOF, "", len(lines), len(lines[-1]) + 1 if lines else 1))
    return tokens


def _lex_number_suffix(rest: str, tokens: list[Token], line: int, col: int) -> None:
    """Lex a numeric suffix (e.g., '5', '60s', '3000ms') from a word tail."""
    # Split into number part and unit part
    i = 0
    while i < len(rest) and (rest[i].isdigit() or rest[i] == "."):
        i += 1
    num_part = rest[:i]
    unit_part = rest[i:]

    if num_part:
        tokens.append(Token(TokenType.NUMBER, num_part, line, col))
        col += len(num_part)

    if unit_part:
        if unit_part in ("s", "ms", "min"):
            tokens.append(Token(TokenType.TIME_UNIT, unit_part, line, col))
        # else: ignore (will be caught by parser as unexpected token)


def _classify_word(word: str, line: int, col: int) -> Token | None:
    """Classify an alphabetic word into its token type."""
    # Check 2-char schedule type prefixes: word might be "FR", "FR5", "VI60s", etc.
    if len(word) >= 2 and word[:2] in SCHEDULE_TYPE_KEYWORDS:
        return Token(TokenType.SCHEDULE_TYPE, word, line, col)

    # 3-char DR modifiers: word might be "DRL", "DRL5s", etc.
    if len(word) >= 3 and word[:3] in DR_KEYWORDS:
        return Token(TokenType.DR_MOD, word, line, col)

    # Exact keyword matches
    if word in SPECIAL_KEYWORDS:
        return Token(TokenType.EXT if word == "EXT" else TokenType.CRF, word, line, col)
    if word in COMBINATOR_KEYWORDS:
        return Token(TokenType.COMBINATOR, word, line, col)
    if len(word) >= 2 and word[:2] == "LH" and (len(word) == 2 or word[2].isdigit() or word[2] == "."):
        return Token(TokenType.LH, word, line, col)
    # LimitedHold alias: "LimitedHold", "LimitedHold10", "LimitedHold10s", etc.
    if len(word) >= 11 and word[:11] == "LimitedHold" and (len(word) == 11 or word[11].isdigit() or word[11] == "."):
        return Token(TokenType.LH, word, line, col)
    if word == "PR":
        return Token(TokenType.PR, word, line, col)
    if word == "Repeat":
        return Token(TokenType.REPEAT, word, line, col)
    if word == "let":
        return Token(TokenType.LET, word, line, col)
    if word in ("hodos", "exponential", "linear"):
        return Token(TokenType.PR_STEP, word, line, col)
    if word in ("start", "increment"):
        return Token(TokenType.PR_PARAM, word, line, col)

    # Identifier: must start with lowercase or underscore
    if word[0].islower() or word[0] == "_":
        if word in LOWERCASE_RESERVED:
            # Reserved words that are not keyword tokens (e.g., "def")
            # Still return as identifier — parser will reject if misused
            return Token(TokenType.IDENTIFIER, word, line, col)
        return Token(TokenType.IDENTIFIER, word, line, col)

    # Uppercase word that doesn't match any keyword
    return Token(TokenType.IDENTIFIER, word, line, col)
