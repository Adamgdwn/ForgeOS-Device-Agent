"""Bounded read-only OOXML text extraction. Never evaluate formulas or fetch links."""
import json
import posixpath
import sys
import zipfile
import xml.etree.ElementTree as ET

LIMIT = 100_000
SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def extract(filename):
    with zipfile.ZipFile(filename) as archive:
        entries = archive.infolist()
        if len(entries) > 4000 or sum(i.file_size for i in entries) > 80_000_000:
            raise ValueError("Office document exceeds extraction limits")
        if len({i.filename for i in entries}) != len(entries):
            raise ValueError("Ambiguous Office archive")

        def xml(name):
            info = archive.getinfo(name)
            if info.file_size > 10_000_000:
                raise ValueError("Office document part exceeds extraction limits")
            data = archive.read(name)
            if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper() or b"\x00" in data:
                raise ValueError("Unsupported XML declarations or encoding")
            return ET.fromstring(data)

        def relationships(part):
            folder, name = posixpath.split(part)
            relfile = posixpath.join(folder, "_rels", name + ".rels")
            if relfile not in archive.namelist():
                return {}
            result = {}
            for rel in xml(relfile):
                if rel.get("TargetMode", "Internal") != "Internal":
                    continue
                target = rel.get("Target", "")
                if not target or ":" in target or "\\" in target or "\x00" in target:
                    raise ValueError("Invalid Office relationship")
                resolved = posixpath.normpath(posixpath.join(folder, target)) if not target.startswith("/") else target[1:]
                if resolved.startswith("../") or resolved.startswith("/"):
                    raise ValueError("Invalid Office relationship")
                result[rel.get("Id")] = (resolved, rel.get("Type", ""))
            return result

        chunks = []
        length = 0
        truncated = False

        def add(text):
            nonlocal length, truncated
            available = LIMIT - length
            if len(text) > available:
                truncated = True
            chunks.append(text[:max(0, available)])
            length += min(len(text), max(0, available))

        if filename.lower().endswith(".xlsx"):
            add("Excel text snapshot. Values are stored values, not recalculated. Formulas show cached results which may be stale or missing. Dates/currency may appear as raw numbers; charts, formatting, comments and external data are not assessed. Open Excel to verify.\n\n")
            part = "xl/workbook.xml"
            rels = relationships(part)
            strings = []
            shared = next((path for path, typ in rels.values() if typ.endswith("/sharedStrings")), None)
            if shared:
                strings = ["".join(n.text or "" for n in item.findall(f".//{{{SS}}}t")) for item in xml(shared)]
            sheets = xml(part).findall(f"{{{SS}}}sheets/{{{SS}}}sheet")
            for sheet in sheets:
                if length >= LIMIT:
                    truncated = True
                    break
                target, typ = rels[sheet.get(f"{{{R}}}id")]
                add(f"## Sheet: {sheet.get('name', 'Unnamed')} ({sheet.get('state', 'visible')})\n")
                if not typ.endswith("/worksheet"):
                    add("[This sheet type is not text-readable.]\n")
                    continue
                for row in xml(target).findall(f"{{{SS}}}sheetData/{{{SS}}}row"):
                    if length >= LIMIT:
                        truncated = True
                        break
                    for cell in row.findall(f"{{{SS}}}c"):
                        value = cell.findtext(f"{{{SS}}}v", "")
                        if cell.get("t") == "s":
                            index = int(value)
                            if index < 0 or index >= len(strings):
                                raise ValueError("Invalid shared string index")
                            value = strings[index]
                        elif cell.get("t") == "inlineStr":
                            value = "".join(n.text or "" for n in cell.findall(f".//{{{SS}}}t"))
                        elif cell.get("t") == "b":
                            value = "TRUE" if value == "1" else "FALSE"
                        formula = cell.find(f"{{{SS}}}f")
                        annotation = f" [formula: {formula.text or 'shared formula'}; cached result]" if formula is not None else ""
                        add(f"{cell.get('r', '?')}: {value}{annotation}\n")
                add("\n")
            if not sheets:
                raise ValueError("No readable spreadsheet sheets")
        else:
            add("PowerPoint text snapshot in slide order. Includes slide text and speaker notes when present. Layout, images, diagrams, charts, animation, embedded files and master text are not assessed. Open PowerPoint to verify.\n\n")
            part = "ppt/presentation.xml"
            rels = relationships(part)
            slides = xml(part).findall(f"{{{P}}}sldIdLst/{{{P}}}sldId")
            for number, slide in enumerate(slides, 1):
                if length >= LIMIT:
                    truncated = True
                    break
                target, typ = rels[slide.get(f"{{{R}}}id")]
                if not typ.endswith("/slide"):
                    raise ValueError("Invalid slide relationship")
                content = xml(target)
                add(f"## Slide {number}" + (" (hidden)" if content.get("show") == "0" else "") + "\n")
                paragraphs = content.findall(f".//{{{A}}}p")
                for paragraph in paragraphs:
                    add("".join(n.text or "" for n in paragraph.findall(f".//{{{A}}}t")) + "\n")
                if not paragraphs:
                    add("[No readable slide text; images may contain information.]\n")
                for note, reltype in relationships(target).values():
                    if reltype.endswith("/notesSlide"):
                        add("Speaker notes:\n")
                        for paragraph in xml(note).findall(f".//{{{A}}}p"):
                            add("".join(n.text or "" for n in paragraph.findall(f".//{{{A}}}t")) + "\n")
                add("\n")
            if not slides:
                raise ValueError("No readable presentation slides")
        return {"text": "".join(chunks), "truncated": truncated}


if __name__ == "__main__":
    try:
        print(json.dumps(extract(sys.argv[1])))
    except Exception:
        sys.exit("Office text could not be read. Open the original in its Office app; encrypted, malformed or oversized parts are unsupported.")
