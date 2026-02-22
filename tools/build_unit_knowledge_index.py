#!/usr/bin/env python3
"""Build a pre-computed unit knowledge index from commentary-knowledge markdown files.

Scans docs/commentary-knowledge/*.md for unit profiles and strategic concepts,
producing a JSON lookup table at tools/data/unit_knowledge_index.json.

Index format:
  {
    "Tarsier": {"snippet": "...", "mechanics": ["breach"]},
    "Shiver Yeti": {"snippet": "...", "mechanics": ["chill"]},
    "_concept_chill": {"snippet": "..."},
    ...
  }

Usage:
    python tools/build_unit_knowledge_index.py
    python tools/build_unit_knowledge_index.py --dry-run   # print stats, don't write
"""
import argparse
import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(SCRIPT_DIR, "..", "docs", "commentary-knowledge")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "data", "unit_knowledge_index.json")

# Base set units (always in every game)
BASE_SET = {
    "Drone", "Engineer", "Conduit", "Blastforge", "Animus",
    "Tarsier", "Rhino", "Wall", "Steelsplitter",
    "Gauss Cannon", "Forcefield",
}

# Mechanic keywords to tag on units
MECHANIC_PATTERNS = {
    "chill": re.compile(r"\bchill\b", re.IGNORECASE),
    "absorb": re.compile(r"\babsorb\b", re.IGNORECASE),
    "breach": re.compile(r"\bbreach\b", re.IGNORECASE),
    "snipe": re.compile(r"\bsnipe\b", re.IGNORECASE),
    "frontline": re.compile(r"\bfrontline\b", re.IGNORECASE),
    "lifespan": re.compile(r"\blifespan\b", re.IGNORECASE),
    "fragile": re.compile(r"\bfragile\b", re.IGNORECASE),
    "prompt": re.compile(r"\bprompt\b", re.IGNORECASE),
    "burst": re.compile(r"\bburst\b", re.IGNORECASE),
    "sacrifice": re.compile(r"\b(?:sac(?:rifice)?|self-sacrifice|self-destruct)\b", re.IGNORECASE),
}

# Headers that are NOT unit names (section headings, tier lists, etc.)
NON_UNIT_HEADERS = {
    "tier 1a", "tier 2a", "tier 2b", "tier 3", "tier 4",
    "economic units", "combat units", "defensive units",
    "principle 1", "principle 2", "principle 3", "principle 4", "principle 5", "principle 6",
    "inflation theory", "barrier value", "resource values",
}


def _is_unit_header(header_text):
    """Check if a ### header is likely a unit name vs a section heading."""
    lower = header_text.lower().strip()
    # Skip known non-unit headers
    if any(lower.startswith(prefix) for prefix in NON_UNIT_HEADERS):
        return False
    # Skip headers with colons (e.g., "Principle 1: Buy Buy Buy")
    if ":" in header_text:
        return False
    # Skip very long headers (unit names are short)
    if len(header_text.split()) > 5:
        return False
    return True


def _extract_snippet(lines, max_sentences=3):
    """Extract a concise snippet from content lines.

    Takes the first few meaningful sentences, skipping source attributions and tables.
    """
    text_parts = []
    for line in lines:
        stripped = line.strip()
        # Skip empty, source attributions, table headers/dividers, and markdown artifacts
        if not stripped:
            continue
        if stripped.startswith(">"):
            continue
        if stripped.startswith("|") or stripped.startswith("---"):
            continue
        if stripped.startswith("#"):
            break  # hit next section
        # Clean markdown formatting (strip list markers, then bold/italic markers)
        clean = re.sub(r"\*+", "", stripped.lstrip("- ")).strip()
        if clean:
            text_parts.append(clean)
        if len(text_parts) >= max_sentences:
            break
    return " ".join(text_parts)


def _detect_mechanics(text):
    """Detect which mechanics are mentioned in text."""
    found = []
    for mech, pattern in MECHANIC_PATTERNS.items():
        if pattern.search(text):
            found.append(mech)
    return sorted(found)


def _parse_table_units(lines):
    """Extract unit entries from markdown tables in sections like Big Absorbers, Key Attackers, etc."""
    units = {}
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Skip header and divider rows
        if stripped.startswith("| Unit") or stripped.startswith("|---"):
            continue
        cols = [c.strip() for c in stripped.split("|")[1:-1]]  # skip empty first/last from split
        if len(cols) >= 2:
            name = cols[0].strip("* ")
            if name and not name.startswith("---"):
                # Build snippet from all columns
                rest = " | ".join(cols[1:])
                snippet = f"{name}: {rest}"
                mechanics = _detect_mechanics(snippet)
                units[name] = {"snippet": snippet, "mechanics": mechanics}
    return units


def parse_base_set_units(filepath):
    """Parse 02-base-set-units.md for base set unit profiles."""
    units = {}
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by ### headers
    sections = re.split(r"^### (.+)$", content, flags=re.MULTILINE)
    # sections[0] is preamble, then alternating (header, body)
    for i in range(1, len(sections), 2):
        header = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        if header in BASE_SET:
            body_lines = body.split("\n")
            snippet = _extract_snippet(body_lines, max_sentences=3)
            mechanics = _detect_mechanics(body)
            if snippet:
                units[header] = {"snippet": snippet, "mechanics": mechanics}
    return units


def parse_advanced_units(filepath):
    """Parse 03-advanced-units.md for advanced unit data.

    Extracts from both ### unit headers and markdown tables.
    """
    units = {}
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # First pass: extract table-based units (Big Absorbers, Key Attackers, Chill Units, etc.)
    sections_by_h2 = re.split(r"^## (.+)$", content, flags=re.MULTILINE)
    for i in range(1, len(sections_by_h2), 2):
        section_title = sections_by_h2[i].strip()
        section_body = sections_by_h2[i + 1] if i + 1 < len(sections_by_h2) else ""

        # Extract from tables
        table_units = _parse_table_units(section_body.split("\n"))
        for name, entry in table_units.items():
            # Add section context to mechanics
            if "absorb" in section_title.lower() and "absorb" not in entry["mechanics"]:
                entry["mechanics"].append("absorb")
                entry["mechanics"].sort()
            if "chill" in section_title.lower() and "chill" not in entry["mechanics"]:
                entry["mechanics"].append("chill")
                entry["mechanics"].sort()
            units[name] = entry

    # Second pass: ### headers for units with prose descriptions
    h3_sections = re.split(r"^### (.+)$", content, flags=re.MULTILINE)
    for i in range(1, len(h3_sections), 2):
        header = h3_sections[i].strip()
        body = h3_sections[i + 1] if i + 1 < len(h3_sections) else ""
        if _is_unit_header(header) and header not in units:
            body_lines = body.split("\n")
            snippet = _extract_snippet(body_lines, max_sentences=3)
            mechanics = _detect_mechanics(body)
            if snippet:
                units[header] = {"snippet": snippet, "mechanics": mechanics}

    return units


def parse_strategy_concepts(filepath):
    """Parse 04-strategy-concepts.md for _concept_* entries."""
    concepts = {}
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Map section titles to concept keys
    concept_map = {
        "absorb": "_concept_absorb",
        "chill": "_concept_chill",
        "breach": "_concept_breach",
        "frontline": "_concept_frontline",
        "snipe": "_concept_snipe",
        "lifespan": "_concept_lifespan",
    }

    sections = re.split(r"^### (.+)$", content, flags=re.MULTILINE)
    for i in range(1, len(sections), 2):
        header = sections[i].strip().lower()
        body = sections[i + 1] if i + 1 < len(sections) else ""

        for keyword, concept_key in concept_map.items():
            if keyword in header and concept_key not in concepts:
                body_lines = body.split("\n")
                snippet = _extract_snippet(body_lines, max_sentences=4)
                if snippet:
                    concepts[concept_key] = {"snippet": snippet}

    # Also check ## headers for broader sections
    h2_sections = re.split(r"^## (.+)$", content, flags=re.MULTILINE)
    for i in range(1, len(h2_sections), 2):
        header = h2_sections[i].strip().lower()
        body = h2_sections[i + 1] if i + 1 < len(h2_sections) else ""

        for keyword, concept_key in concept_map.items():
            if keyword in header and concept_key not in concepts:
                body_lines = body.split("\n")
                snippet = _extract_snippet(body_lines, max_sentences=4)
                if snippet:
                    concepts[concept_key] = {"snippet": snippet}

    return concepts


def build_index():
    """Build the complete unit knowledge index."""
    index = {}

    # 1. Base set units
    base_path = os.path.join(KB_DIR, "02-base-set-units.md")
    if os.path.exists(base_path):
        base_units = parse_base_set_units(base_path)
        index.update(base_units)

    # 2. Advanced units
    adv_path = os.path.join(KB_DIR, "03-advanced-units.md")
    if os.path.exists(adv_path):
        adv_units = parse_advanced_units(adv_path)
        index.update(adv_units)

    # 3. Strategy concepts
    strat_path = os.path.join(KB_DIR, "04-strategy-concepts.md")
    if os.path.exists(strat_path):
        concepts = parse_strategy_concepts(strat_path)
        index.update(concepts)

    return index


def main():
    parser = argparse.ArgumentParser(description="Build unit knowledge index from KB markdown")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing")
    args = parser.parse_args()

    index = build_index()

    unit_count = sum(1 for k in index if not k.startswith("_concept_"))
    concept_count = sum(1 for k in index if k.startswith("_concept_"))

    print(f"Units indexed: {unit_count}")
    print(f"Concepts indexed: {concept_count}")
    print(f"Total entries: {len(index)}")

    # Show mechanic distribution
    all_mechs = {}
    for entry in index.values():
        for m in entry.get("mechanics", []):
            all_mechs[m] = all_mechs.get(m, 0) + 1
    if all_mechs:
        print(f"Mechanics: {dict(sorted(all_mechs.items(), key=lambda x: -x[1]))}")

    if args.dry_run:
        print("\n[DRY RUN] Would write to:", OUTPUT_PATH)
        # Print sample entries
        sample_keys = list(index.keys())[:5]
        for k in sample_keys:
            snippet = index[k]["snippet"][:80] + "..." if len(index[k]["snippet"]) > 80 else index[k]["snippet"]
            print(f"  {k}: {snippet}")
        return

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    print(f"Written to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
