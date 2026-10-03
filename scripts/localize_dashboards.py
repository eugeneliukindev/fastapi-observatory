"""Build the dashboard Grafana loads: the English source once per language, switched by a variable."""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_GRAFANA: Final = Path(__file__).resolve().parent.parent / "observability" / "grafana"
_SOURCE: Final = _GRAFANA / "source" / "api.json"
_DICTIONARIES: Final = _GRAFANA / "source" / "i18n"
_TARGET: Final = _GRAFANA / "dashboards" / "api.json"

_SOURCE_LANGUAGE_CODE: Final = "en"
_SOURCE_LANGUAGE_NAME: Final = "English"
_LANGUAGE_VARIABLE: Final = "language"
_PANEL_IDS_PER_LANGUAGE: Final = 1000

# A variable or a label stays as it is in every language: Grafana substitutes it.
_PLACEHOLDER: Final = re.compile(r"\{\{[^}]*\}\}|\$\{[^}]*\}|\$\w+")
_GRAFANA_KEYWORDS: Final = frozenset({"__auto"})

type _Json = dict[str, _Json] | list[_Json] | str | int | float | bool | None
type _Object = dict[str, _Json]


class _Text(NamedTuple):
    """A string a reader sees, and where it lives."""

    holder: _Object
    key: str
    source: str


class _Language(NamedTuple):
    """A language the dashboard speaks: its code, its own name for itself and its translation."""

    code: str
    name: str
    translate: Callable[[str], str]


def main() -> None:
    """Write the dashboard, or list what is wrong with the dictionaries."""
    source = _load(_SOURCE)
    sources = list(dict.fromkeys(text.source for text in _texts_in_content(source)))
    languages = [_Language(_SOURCE_LANGUAGE_CODE, _SOURCE_LANGUAGE_NAME, str)]
    problems: list[str] = []
    for path in sorted(_DICTIONARIES.glob("*.json")):
        name, texts = _load_dictionary(path)
        problems.extend(_find_problems(path.stem, texts, sources))
        languages.append(_Language(path.stem, name, texts.__getitem__))
    if problems:
        sys.exit("\n".join(problems))

    dashboard = _combine(source, languages)
    _TARGET.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _load(path: Path) -> _Object:
    loaded: _Json = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} holds {type(loaded).__name__}, not an object")
    return loaded


def _load_dictionary(path: Path) -> tuple[str, dict[str, str]]:
    dictionary = _load(path)
    name = dictionary.get("name")
    texts = _object(dictionary, "texts")
    if not isinstance(name, str):
        raise TypeError(f"{path}: `name`, the language's name for itself, is not a string")
    not_strings = [source for source, translation in texts.items() if not isinstance(translation, str)]
    if not_strings:
        raise TypeError(f"{path}: translations that are not strings: {not_strings}")
    return name, {source: str(translation) for source, translation in texts.items()}


def _find_problems(language: str, texts: dict[str, str], sources: list[str]) -> Iterator[str]:
    for source in sources:
        translation = texts.get(source)
        if translation is None:
            yield f"{language}: no translation for {source!r}"
        elif sorted(_PLACEHOLDER.findall(source)) != sorted(_PLACEHOLDER.findall(translation)):
            yield f"{language}: {source!r} and {translation!r} differ in variables or labels"
    yield from (f"{language}: {source!r} is not on the dashboard" for source in texts.keys() - set(sources))


def _combine(source: _Object, languages: list[_Language]) -> _Object:
    dashboard = copy.deepcopy(source)
    spec = _object(dashboard, "spec")
    elements: _Object = {}
    sections: list[_Json] = []
    for index, language in enumerate(languages):
        content = _localize(source, language, index)
        elements.update(_object(content, "elements"))
        sections.append(
            {
                "kind": "RowsLayoutRow",
                "spec": {
                    "title": language.name,
                    "hideHeader": True,
                    "conditionalRendering": _shown_for(language.code),
                    "layout": _object(content, "layout"),
                },
            }
        )
    spec["elements"] = elements
    spec["layout"] = {"kind": "RowsLayout", "spec": {"rows": sections}}
    spec["variables"] = [_language_variable(languages), *_objects(spec, "variables")]
    return dashboard


def _localize(source: _Object, language: _Language, index: int) -> _Object:
    """Return the source's layout and elements in one language, its elements renamed apart."""
    content = copy.deepcopy(_object(source, "spec"))
    # Collected before anything changes: whether a field reference is translated depends on the
    # English names the panel gives its fields.
    for text in list(_texts_in_content(source={"spec": content})):
        text.holder[text.key] = language.translate(text.source)

    suffix = "" if language.code == _SOURCE_LANGUAGE_CODE else f"-{language.code}"
    renamed: _Object = {}
    for name, element in _object(content, "elements").items():
        if not isinstance(element, dict):
            raise TypeError(f"element {name!r} is {type(element).__name__}, not an object")
        panel = _object(element, "spec")
        panel_id = panel.get("id")
        if isinstance(panel_id, int):
            panel["id"] = panel_id + index * _PANEL_IDS_PER_LANGUAGE
        renamed[name + suffix] = element
    for reference in _element_references(_object(content, "layout")):
        reference["name"] = f"{reference['name']}{suffix}"
    return {"elements": renamed, "layout": _object(content, "layout")}


def _shown_for(language_code: str) -> _Object:
    condition: _Object = {"variable": _LANGUAGE_VARIABLE, "operator": "equals", "value": language_code}
    return {
        "kind": "ConditionalRenderingGroup",
        "spec": {
            "visibility": "show",
            "condition": "and",
            "items": [{"kind": "ConditionalRenderingVariable", "spec": condition}],
        },
    }


def _language_variable(languages: list[_Language]) -> _Object:
    options: list[_Json] = [
        {"selected": language.code == _SOURCE_LANGUAGE_CODE, "text": language.name, "value": language.code}
        for language in languages
    ]
    return {
        "kind": "CustomVariable",
        "spec": {
            "name": _LANGUAGE_VARIABLE,
            "query": ",".join(f"{language.name} : {language.code}" for language in languages),
            "current": {"text": _SOURCE_LANGUAGE_NAME, "value": _SOURCE_LANGUAGE_CODE},
            "options": options,
            "multi": False,
            "includeAll": False,
            "label": "Language",
            "hide": "dontHide",
            "skipUrlSync": False,
            "allowCustomValue": False,
        },
    }


def _element_references(layout: _Object) -> Iterator[_Object]:
    layout_spec = _object(layout, "spec")
    for item in _objects(layout_spec, "items"):
        yield _object(_object(item, "spec"), "element")
    for section in [*_objects(layout_spec, "rows"), *_objects(layout_spec, "tabs")]:
        yield from _element_references(_object(_object(section, "spec"), "layout"))


def _texts_in_content(source: _Object) -> Iterator[_Text]:
    """Yield the texts of the rows and the panels — what the language variable switches."""
    spec = _object(source, "spec")
    yield from _texts_in_layout(_object(spec, "layout"))
    for element in _object(spec, "elements").values():
        if not isinstance(element, dict):
            raise TypeError(f"an element is {type(element).__name__}, not an object")
        yield from _texts_in_panel(_object(element, "spec"))


def _texts_in_layout(layout: _Object) -> Iterator[_Text]:
    layout_spec = _object(layout, "spec")
    for section in [*_objects(layout_spec, "rows"), *_objects(layout_spec, "tabs")]:
        section_spec = _object(section, "spec")
        yield from _texts(section_spec, "title")
        yield from _texts_in_layout(_object(section_spec, "layout"))


def _texts_in_panel(panel: _Object) -> Iterator[_Text]:
    yield from _texts(panel, "title", "description")
    for link in _objects(panel, "links"):
        yield from _texts(link, "title")

    data = _object(_object(panel, "data"), "spec")
    queries = [_object(_object(_object(query, "spec"), "query"), "spec") for query in _objects(data, "queries")]
    renames = [
        _object(_object(_object(transformation, "spec"), "options"), "renameByName")
        for transformation in _objects(data, "transformations")
    ]
    sorts = [
        sort
        for transformation in _objects(data, "transformations")
        for sort in _objects(_object(_object(transformation, "spec"), "options"), "sort")
    ]
    field_config = _object(_object(_object(panel, "vizConfig"), "spec"), "fieldConfig")
    overrides = _objects(field_config, "overrides")
    field_names = _field_names_given(queries, renames, overrides)

    for query in queries:
        yield from _texts(query, "legendFormat")
    for rename in renames:
        yield from _texts(rename, *rename)
    for sort in sorts:
        yield from _field_references(sort, "field", field_names)
    yield from _texts_in_field_settings(_object(field_config, "defaults"))
    for override in overrides:
        matcher = _object(override, "matcher")
        if matcher.get("id") == "byName":
            yield from _field_references(matcher, "options", field_names)
        for field_property in _objects(override, "properties"):
            yield from _texts_in_field_property(field_property)


def _field_names_given(queries: list[_Object], renames: list[_Object], overrides: list[_Object]) -> set[str]:
    """Return the field names the panel itself sets, as opposed to the ones its data brings."""
    legends = [query.get("legendFormat") for query in queries]
    renamed = [name for rename in renames for name in rename.values()]
    displayed = [
        field_property.get("value")
        for override in overrides
        for field_property in _objects(override, "properties")
        if field_property.get("id") == "displayName"
    ]
    return {name for name in [*legends, *renamed, *displayed] if isinstance(name, str)}


def _field_references(holder: _Object, key: str, field_names: set[str]) -> Iterator[_Text]:
    reference = holder.get(key)
    if isinstance(reference, str) and reference in field_names:
        yield _Text(holder, key, reference)


def _texts_in_field_settings(settings: _Object) -> Iterator[_Text]:
    yield from _texts(settings, "displayName")
    yield from _texts(_object(settings, "custom"), "axisLabel")
    for link in _objects(settings, "links"):
        yield from _texts(link, "title")
    for mapping in _objects(settings, "mappings"):
        yield from _texts_in_value_mapping(mapping)


def _texts_in_field_property(field_property: _Object) -> Iterator[_Text]:
    match field_property.get("id"):
        case "displayName":
            yield from _texts(field_property, "value")
        case "links":
            for link in _objects(field_property, "value"):
                yield from _texts(link, "title")
        case "mappings":
            for mapping in _objects(field_property, "value"):
                yield from _texts_in_value_mapping(mapping)
        case _:
            return


def _texts_in_value_mapping(mapping: _Object) -> Iterator[_Text]:
    options = _object(mapping, "options")
    # A range, a regex and a special value map to one result; a value mapping maps each value.
    results = [options["result"]] if "result" in options else list(options.values())
    for result in results:
        if isinstance(result, dict):
            yield from _texts(result, "text")


def _texts(holder: _Object, *keys: str) -> Iterator[_Text]:
    for key in keys:
        value = holder.get(key)
        if isinstance(value, str) and _is_readable(value):
            yield _Text(holder, key, value)


def _is_readable(value: str) -> bool:
    return value not in _GRAFANA_KEYWORDS and any(char.isalpha() for char in _PLACEHOLDER.sub("", value))


def _object(holder: _Object, key: str) -> _Object:
    value = holder.get(key, {})
    if not isinstance(value, dict):
        raise TypeError(f"{key!r} is {type(value).__name__}, not an object")
    return value


def _objects(holder: _Object, key: str) -> list[_Object]:
    values = holder.get(key, [])
    if not isinstance(values, list) or not all(isinstance(value, dict) for value in values):
        raise TypeError(f"{key!r} is not a list of objects")
    return [value for value in values if isinstance(value, dict)]


if __name__ == "__main__":
    main()
