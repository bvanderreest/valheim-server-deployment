"""The log fixture is committed to a PUBLIC repo. Nothing real may be in it.

This exists because sanitising it nearly failed silently. The Steam id appears
as `Steam_76561198210919477`, the redaction used `\\b7656\\d{13}\\b`, and `\\b`
does not match after an underscore — so it never fired. Worse, the "did it
work" check counted matches of the SAME pattern afterwards and reported zero,
because the pattern was wrong in both directions. A real person's Steam id was
one commit from being published.

So these assertions look for the SHAPES of identifiers, not for the specific
values that were redacted. A test that only knows the values it already removed
cannot catch the next one.
"""
import re
from pathlib import Path

import pytest

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.log"))

# Shapes, anchored loosely on purpose — see the module docstring.
FORBIDDEN = {
    "steam id": r"7656\d{13}(?<!76561190000000000)",
    "long base64 blob (lobby token)": r"[A-Za-z0-9+/]{80,}",
    "real-looking GUID": r"\b(?!00000000-0000-0000-0000-000000000000)"
                        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
}


def test_there_is_at_least_one_fixture():
    """Otherwise every test below passes by having nothing to check."""
    assert FIXTURES


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
@pytest.mark.parametrize("label,pattern", list(FORBIDDEN.items()))
def test_no_real_identifiers_in_committed_logs(path, label, pattern):
    hits = re.findall(pattern, path.read_text(errors="replace"))
    assert not hits, f"{path.name} contains {label}: {hits[:2]}"


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_public_ips_are_documentation_ranges_only(path):
    """RFC 5737 reserves 192.0.2.0/24, 198.51.100.0/24 and 203.0.113.0/24 for
    documentation. Anything else routable is somebody's real address."""
    text = path.read_text(errors="replace")
    for ip in set(re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)):
        octets = [int(o) for o in ip.split(".")]
        if any(o > 255 for o in octets):
            continue
        private = (octets[0] in (10, 127) or octets[:2] == [192, 168]
                   or (octets[0] == 172 and 16 <= octets[1] <= 31)
                   or octets[0] == 0 or octets[0] >= 224)
        documentation = (octets[:3] in ([192, 0, 2], [198, 51, 100], [203, 0, 113]))
        assert private or documentation, f"{path.name} contains a routable IP: {ip}"


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_the_sanitisation_is_declared_in_the_file(path):
    """So the next person does not paste a raw log over the top of it."""
    head = path.read_text(errors="replace")[:600].lower()
    assert "sanitised" in head and "public" in head, (
        f"{path.name} does not say it is sanitised; the next person will not know")
