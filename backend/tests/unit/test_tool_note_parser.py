from types import SimpleNamespace

from library.tool_note_parser import apply_note_to_tool, parse_tool_note, pricing_type_from_text

HTTPING = """---
tags:
  - wiedza/informatyka
---
**Purpose:** testowanie serwerów WWW
**Type of application**: console tool
**Licence**:GPL
**homepage**:
works on: Linux, Macos (brew)
### Key Points:

- point1
- poin2

### Important Commands:

Example of commands:
```

```


### Additional Notes:


## Source of note
[[docker swarm Udemy]]


creation date: 2025-05-22 06:11
"""

SEMGREP = """---
tags:
  - wiedza/informatyka
---
## Semgrep

**Purpose:** Scanning of code
**Type of application**: console
**Licence**: commercial
**homepage**: https://semgrep.dev/
**github page**: https://github.com/semgrep/semgrep
**Pricing type**: free / paid pro version
**pricing page**: https://semgrep.dev/pricing (startups can get special prices :) )
### Key Points:

- Rules are YAML
- point1

- poin2

### Important Commands:

Example of commands:
```
semgrep --config=auto
```
## Ignoring rules
  see: https://semgrep.dev/docs/ignoring

### Additional Notes:

## CI/CD
### Jenkins

```
stage('Semgrep Scan') {
}
```

## Connected notes
## External Links

## Source of note
[[Szkolenie]]
"""

JQ = """---
tags:
  - wiedza/informatyka
---
## jq

**Purpose:** Parse json output

### Key Points:

-
### Important Commands:

#### dodanie zmiennej
```
jq --arg value1 x
```

### Additional Notes:

- there is also command for parsing yaml called [[yq]]
"""


class TestParseToolNote:
    def test_template_placeholders_are_not_content(self):
        parsed = parse_tool_note(HTTPING)

        assert parsed == {
            "purpose": "testowanie serwerów WWW",
            "app_type": "console tool",
            "license": "GPL",
            "works_on": "Linux, Macos (brew)",
        }

    def test_full_note_maps_every_section(self):
        parsed = parse_tool_note(SEMGREP)

        assert parsed["purpose"] == "Scanning of code"
        assert parsed["homepage_url"] == "https://semgrep.dev/"
        assert parsed["github_url"] == "https://github.com/semgrep/semgrep"
        assert parsed["pricing_url"] == "https://semgrep.dev/pricing"
        assert parsed["pricing_type"] == "freemium"
        assert parsed["pricing"] == "free / paid pro version"
        assert parsed["key_points"] == ["Rules are YAML"]
        assert "semgrep --config=auto" in parsed["important_commands"]
        assert "Ignoring rules" in parsed["important_commands"]
        assert "Example of commands" not in parsed["important_commands"]
        assert "stage('Semgrep Scan')" in parsed["personal_notes"]
        assert "Szkolenie" not in parsed["personal_notes"]

    def test_note_without_labels_still_yields_commands_and_notes(self):
        parsed = parse_tool_note(JQ)

        assert parsed["purpose"] == "Parse json output"
        assert "key_points" not in parsed
        assert "#### dodanie zmiennej" in parsed["important_commands"]
        assert parsed["personal_notes"].startswith("- there is also command")

    def test_non_github_link_is_not_taken_as_repository(self):
        parsed = parse_tool_note("**github page**: https://example.com/not-github\n### Key Points:\n")

        assert "github_url" not in parsed

    def test_overlong_licence_is_dropped(self):
        parsed = parse_tool_note("**Licence**: " + "x" * 120 + "\n### Key Points:\n")

        assert "license" not in parsed


class TestPricingType:
    def test_maps_free_text_to_closed_list(self):
        assert pricing_type_from_text("free") == "free"
        assert pricing_type_from_text("free / paid pro version") == "freemium"
        assert pricing_type_from_text("commercial") == "paid"
        assert pricing_type_from_text("subscription per seat") == "subscription"
        assert pricing_type_from_text("") is None
        assert pricing_type_from_text("wiem co") is None


class TestApplyNoteToTool:
    def _tool(self, **fields):
        base = dict(purpose=None, app_type=None, license=None, works_on=None, key_points=[], personal_notes=None)
        base.update(fields)
        return SimpleNamespace(**base)

    def test_fills_only_empty_fields(self):
        tool = self._tool(license="MIT", key_points=[])

        changed = apply_note_to_tool(tool, {"license": "GPL", "purpose": "x", "key_points": ["a"]})

        assert tool.license == "MIT"
        assert tool.purpose == "x"
        assert tool.key_points == ["a"]
        assert sorted(changed) == ["key_points", "purpose"]

    def test_overwrite_replaces_existing_values(self):
        tool = self._tool(license="MIT")

        changed = apply_note_to_tool(tool, {"license": "GPL"}, overwrite=True)

        assert tool.license == "GPL"
        assert changed == ["license"]

    def test_same_value_is_not_reported_as_change(self):
        tool = self._tool()

        assert apply_note_to_tool(tool, {"license": None}) == []
