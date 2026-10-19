"""Минимальный читатель формата .NET Remoting Binary Format (MS-NRBF).

Именно в нём старая программа (UsbMonitor/TURZX) хранит темы и настройки
(файлы *.data, записанные через BinaryFormatter). Код ничего не исполняет,
только разбирает данные в обычные словари/списки Python.
"""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from typing import Any


class NrbfError(Exception):
    pass


@dataclass
class NClass:
    """Объект .NET: имя класса и поля."""

    name: str
    fields: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.fields:
            return self.fields[key]
        # автосвойства C# хранятся как "<Name>k__BackingField"
        bf = f"<{key}>k__BackingField"
        return self.fields.get(bf, default)

    def __repr__(self) -> str:  # pragma: no cover - для отладки
        return f"NClass({self.name}, {list(self.fields)})"


@dataclass
class _Ref:
    id: int


@dataclass
class _ClassMeta:
    name: str
    members: list[str]
    btypes: list[int] | None
    extra: list[Any] | None


_PRIM_FMT = {
    1: "<?", 2: "<B", 6: "<d", 7: "<h", 8: "<i", 9: "<q", 10: "<b",
    11: "<f", 12: "<q", 13: "<Q", 14: "<H", 15: "<I", 16: "<Q",
}


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.f = io.BytesIO(data)
        self.objects: dict[int, Any] = {}
        self.metas: dict[int, _ClassMeta] = {}

    # ---- примитивы ----
    def read(self, n: int) -> bytes:
        b = self.f.read(n)
        if len(b) != n:
            raise NrbfError("неожиданный конец файла")
        return b

    def u8(self) -> int:
        return self.read(1)[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def lps(self) -> str:
        length = 0
        shift = 0
        for _ in range(5):
            b = self.u8()
            length |= (b & 0x7F) << shift
            if not b & 0x80:
                break
            shift += 7
        return self.read(length).decode("utf-8", errors="replace")

    def prim(self, t: int) -> Any:
        if t in _PRIM_FMT:
            fmt = _PRIM_FMT[t]
            return struct.unpack(fmt, self.read(struct.calcsize(fmt)))[0]
        if t == 3:  # Char, UTF-8
            first = self.u8()
            n = 1 if first < 0x80 else 2 if first < 0xE0 else 3 if first < 0xF0 else 4
            return (bytes([first]) + self.read(n - 1)).decode("utf-8", errors="replace")
        if t in (5, 18):  # Decimal, String
            return self.lps()
        if t == 17:
            return None
        raise NrbfError(f"неизвестный примитивный тип {t}")

    # ---- записи ----
    def class_info(self) -> tuple[int, str, list[str]]:
        oid = self.i32()
        name = self.lps()
        cnt = self.i32()
        return oid, name, [self.lps() for _ in range(cnt)]

    def member_type_info(self, cnt: int) -> tuple[list[int], list[Any]]:
        btypes = [self.u8() for _ in range(cnt)]
        extra: list[Any] = []
        for bt in btypes:
            if bt in (0, 7):
                extra.append(self.u8())
            elif bt == 3:
                extra.append(self.lps())
            elif bt == 4:
                extra.append((self.lps(), self.i32()))
            else:
                extra.append(None)
        return btypes, extra

    def read_class_values(self, oid: int, meta: _ClassMeta) -> NClass:
        obj = NClass(meta.name)
        self.objects[oid] = obj
        for i, m in enumerate(meta.members):
            if meta.btypes is not None and meta.btypes[i] == 0:
                obj.fields[m] = self.prim(meta.extra[i])
            else:
                obj.fields[m] = self.record()
        return obj

    def record(self) -> Any:
        rt = self.u8()
        if rt == 0:
            self.read(16)
            return self.record()
        if rt in (2, 3, 4, 5):
            oid, name, members = self.class_info()
            btypes = extra = None
            if rt in (4, 5):
                btypes, extra = self.member_type_info(len(members))
            if rt in (3, 5):
                self.i32()  # libraryId
            meta = _ClassMeta(name, members, btypes, extra)
            self.metas[oid] = meta
            return self.read_class_values(oid, meta)
        if rt == 1:
            oid = self.i32()
            meta = self.metas[self.i32()]
            return self.read_class_values(oid, meta)
        if rt == 6:
            oid = self.i32()
            s = self.lps()
            self.objects[oid] = s
            return s
        if rt == 7:
            return self.binary_array()
        if rt == 8:
            return self.prim(self.u8())
        if rt == 9:
            return _Ref(self.i32())
        if rt == 10:
            return None
        if rt == 11:
            return _End
        if rt == 12:
            self.i32()
            self.lps()
            return self.record()
        if rt == 13:
            return _Nulls(self.u8())
        if rt == 14:
            return _Nulls(self.i32())
        if rt == 15:
            oid = self.i32()
            n = self.i32()
            t = self.u8()
            if t == 2:
                val: Any = self.read(n)
            else:
                val = [self.prim(t) for _ in range(n)]
            self.objects[oid] = val
            return val
        if rt in (16, 17):
            oid = self.i32()
            n = self.i32()
            arr: list[Any] = []
            self.objects[oid] = arr
            self.fill_records(arr, n)
            return arr
        raise NrbfError(f"неизвестный тип записи {rt}")

    def fill_records(self, arr: list[Any], n: int) -> None:
        while len(arr) < n:
            r = self.record()
            if isinstance(r, _Nulls):
                arr.extend([None] * r.n)
            else:
                arr.append(r)

    def binary_array(self) -> Any:
        oid = self.i32()
        atype = self.u8()
        rank = self.i32()
        lengths = [self.i32() for _ in range(rank)]
        if atype in (3, 4, 5):
            for _ in range(rank):
                self.i32()
        bt, extra = self.member_type_info(1)
        total = 1
        for ln in lengths:
            total *= ln
        arr: list[Any] = []
        self.objects[oid] = arr
        if bt[0] == 0:
            arr.extend(self.prim(extra[0]) for _ in range(total))
        else:
            self.fill_records(arr, total)
        return arr

    # ---- разрешение ссылок ----
    def resolve(self, v: Any, seen: set[int]) -> Any:
        if isinstance(v, _Ref):
            target = self.objects.get(v.id)
            if target is None:
                return None
            return self.resolve(target, seen)
        if isinstance(v, NClass):
            if id(v) in seen:
                return v
            seen.add(id(v))
            for k, x in v.fields.items():
                v.fields[k] = self.resolve(x, seen)
            return v
        if isinstance(v, list):
            if id(v) in seen:
                return v
            seen.add(id(v))
            for i, x in enumerate(v):
                v[i] = self.resolve(x, seen)
            return v
        return v


class _EndT:
    pass


_End = _EndT()


@dataclass
class _Nulls:
    n: int


def loads(data: bytes) -> Any:
    """Разобрать NRBF-поток и вернуть корневой объект."""
    r = _Reader(data)
    if r.u8() != 0:
        raise NrbfError("это не файл BinaryFormatter")
    root_id = r.i32()
    r.read(12)
    while True:
        rec = r.record()
        if rec is _End:
            break
    root = r.objects.get(root_id)
    return r.resolve(root, set())


def generic_list(v: Any) -> list[Any]:
    """System.Collections.Generic.List<T> -> обычный список."""
    if isinstance(v, NClass) and "_items" in v.fields:
        items = v.fields.get("_items") or []
        size = v.fields.get("_size", len(items))
        return list(items[:size])
    if isinstance(v, list):
        return v
    return []
