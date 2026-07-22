from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LayoutItem:
    field: str | None = None
    custom_link: str | None = None
    behavior: str = "Required"
    sort_order: int | None = None
    empty: bool = False
    ui_behavior: str | None = None


@dataclass
class LayoutColumn:
    items: list[LayoutItem] = field(default_factory=list)
    reserved: str | None = None


@dataclass
class LayoutSection:
    label: str = ""
    collapsible: bool = False
    columns: int = 1
    heading: str | None = None
    layout_columns: list[LayoutColumn] = field(default_factory=list)
    edit_layout_sections: list[LayoutSection] | None = None


@dataclass
class RelatedListItem:
    object_name: str
    label: str = ""
    fields: list[str] = field(default_factory=list)
    sort_field: str | None = None
    sort_order: str = "Asc"
    related_list: str | None = None
    custom: bool = False


@dataclass
class MiniLayout:
    object_name: str
    fields: list[str] = field(default_factory=list)
    related_lists: list[RelatedListItem] = field(default_factory=list)


@dataclass
class Layout:
    name: str
    object_type: str = ""
    component_id: str | None = None
    sections: list[LayoutSection] = field(default_factory=list)
    related_lists: list[RelatedListItem] = field(default_factory=list)
    mini_layouts: list[MiniLayout] = field(default_factory=list)
    quick_actions: list[dict] = field(default_factory=list)
