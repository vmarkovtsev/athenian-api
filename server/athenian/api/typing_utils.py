import dataclasses
from datetime import datetime, timedelta
from itertools import chain
import sys
from typing import Any, Callable, Iterable, Iterator, Mapping, NamedTuple, Optional, TypeVar, Union

import numpy as np
import pandas as pd
from pandas._libs import tslib
import sentry_sdk

from athenian.api.tracing import sentry_span

OriginalSpecialForm = type(Any)

if sys.version_info < (3, 10):

    class _VerbatimOptional(OriginalSpecialForm, _root=True):
        cache = {}

        def __init__(self):
            super().__init__(
                "Optional",
                """
            Alternative Optional that prevents coercing (), [], and {} attributes to null during
            serialization.
            """,
            )

        def __getitem__(self, parameters):
            typeobj = super().__getitem__(parameters)
            key = typeobj.__origin__.__reduce__()
            try:
                typeobj.__origin__ = self.cache[key]
            except KeyError:
                cloned_origin = self.cache[key] = OriginalSpecialForm.__new__(OriginalSpecialForm)
                for attr in self.__slots__:
                    setattr(cloned_origin, attr, getattr(typeobj.__origin__, attr))
                typeobj.__origin__ = cloned_origin
            typeobj.__origin__.__verbatim__ = True
            return typeobj

    VerbatimOptional = _VerbatimOptional()
    VerbatimUnionTypes = (Union,)
else:

    class _VerbatimUnion(OriginalSpecialForm, _root=True):
        __slots__ = ("__verbatim__",)

        def __init__(self):
            self._getitem = Union._getitem
            self._name = Union._name
            self.__verbatim__ = True

    VerbatimUnion = _VerbatimUnion()

    @OriginalSpecialForm
    def VerbatimOptional(self, parameters):
        """Alternative Optional that prevents coercing (), [], and {} attributes to null during \
        serialization."""
        return VerbatimUnion[Optional[parameters].__args__]

    VerbatimUnionTypes = (VerbatimUnion, Union)


def is_generic(klass: type):
    """Determine whether klass is a generic class."""
    return hasattr(klass, "__origin__")


def is_dict(klass: type):
    """Determine whether klass is a dict."""
    return getattr(klass, "__origin__", None) == dict


def is_list(klass: type):
    """Determine whether klass is a list."""
    return getattr(klass, "__origin__", None) == list


def is_union(klass: type):
    """Determine whether klass is a Union."""
    return getattr(klass, "__origin__", None) in VerbatimUnionTypes


def is_optional(klass: type):
    """Determine whether klass is an Optional."""
    return (
        is_union(klass) and len(klass.__args__) == 2 and issubclass(klass.__args__[1], type(None))
    )


def wraps(wrapper, wrappee):
    """Alternative to functools.wraps() for async functions."""  # noqa: D402
    wrapper.__name__ = wrappee.__name__
    wrapper.__qualname__ = wrappee.__qualname__
    wrapper.__module__ = wrappee.__module__
    wrapper.__doc__ = wrappee.__doc__
    wrapper.__annotations__ = wrappee.__annotations__
    wrapper.__wrapped__ = wrappee
    return wrapper


NST = TypeVar("NST")


class NumpyStruct(Mapping[str, Any]):
    """
    Constrained dataclass based on numpy structured array.

    We divide the fields into two groups: mutable and immutable.
    The mutable fields are stored as regular class members and discarded from serialization.
    The immutable fields are not materialized explicitly. Instead, they are taken from numpy
    structured array (`_arr`) that references an arbitrary memory buffer (`_data`).
    Serialization of the class is as simple as exposing the underlying memory buffer outside.

    We support variable-length sub-arrays using the special notation `[<array dtype>]`. That way
    the arrays are appended to `_data`, and `_arr` points to them by pairs (offset, length).
    """

    dtype: np.dtype
    nested_dtypes: Mapping[str, np.dtype]

    def __init__(self, data: Union[bytes, bytearray, memoryview, np.ndarray], **optional: Any):
        """Initialize a new instance of NumpyStruct from raw memory and the (perhaps incomplete) \
        mapping of mutable field values."""
        if isinstance(data, (np.ndarray, np.void)):
            assert data.shape == () or data.shape == (1,)
            data = data.reshape(1)
            self._data = data.view(np.uint8).data
            self._arr = data
        else:
            self._data = data
            self._arr = None
        for attr in self.__slots__[2:]:
            setattr(self, attr, optional.get(attr))

    @classmethod
    def from_fields(cls: NST, **kwargs: Any) -> NST:
        """Initialize a new instance of NumpyStruct from the mapping of immutable field \
        values."""
        arr = np.zeros(1, cls.dtype)
        extra_bytes = []
        offset = cls.dtype.itemsize
        for field_name, (field_dtype, _) in cls.dtype.fields.items():
            value = kwargs.pop(field_name)
            try:
                nested_dtype = cls.nested_dtypes[field_name]
            except KeyError:
                if value is None and field_dtype.char in ("S", "U"):
                    value = ""
                if field_dtype.char == "M" and isinstance(value, datetime):
                    value = value.replace(tzinfo=None)
                arr[field_name] = np.asarray(value, field_dtype)
            else:
                if is_str := (
                    (is_ascii := _dtype_is_ascii(nested_dtype)) or nested_dtype.char in ("S", "U")
                ):
                    if isinstance(value, np.ndarray):
                        if value.dtype == np.dtype(object):
                            nan_mask = value == np.array([None])
                        else:
                            nan_mask = np.full(len(value), False)
                    else:
                        nan_mask = np.fromiter(
                            (v is None for v in value), dtype=np.bool_, count=len(value),
                        )
                    if is_ascii:
                        nested_dtype = np.dtype("S")
                value = np.asarray(value, nested_dtype)
                assert len(value.shape) == 1, "we don't support arrays of more than 1 dimension"
                if is_str and nan_mask.any():
                    if not value.flags.writeable:
                        value = value.copy()
                    value[nan_mask] = ""
                extra_bytes.append(data := value.view(np.byte).data)
                pointer = [offset, len(value)]
                if is_str and (is_ascii or nested_dtype.itemsize == 0):
                    pointer.append(
                        value.dtype.itemsize // np.dtype(nested_dtype.char + "1").itemsize,
                    )
                arr[field_name] = pointer
                offset += len(data)
        if not extra_bytes:
            return cls(arr.view(np.byte).data)
        return cls(b"".join(chain([arr.view(np.byte).data], extra_bytes)), **kwargs)

    @property
    def data(self) -> bytes:
        """Return the underlying memory."""
        return self._data

    @property
    def array(self) -> np.ndarray:
        """Return the underlying numpy array that wraps `data`."""
        if self._arr is None:
            self._arr = np.frombuffer(self.data, self.dtype, count=1)
        return self._arr

    @property
    def coerced_data(self) -> memoryview:
        """Return prefix of `data` with nested immutable objects excluded."""
        return memoryview(self.data)[: self.dtype.itemsize]

    def __getitem__(self, item: str) -> Any:
        """Implement self[]."""
        return getattr(self, item)

    def __setitem__(self, key: str, value: Any) -> None:
        """Implement self[] = ..."""
        setattr(self, key, value)

    def __len__(self) -> int:
        """Implement len()."""
        return len(self.dtype) + len(self.__slots__) - 2

    def __iter__(self) -> Iterator[str]:
        """Implement iter()."""
        return iter(chain(self.dtype.names, self.__slots__[2:]))

    def __hash__(self) -> int:
        """Implement hash()."""
        return hash(self._data)

    def __str__(self) -> str:
        """Format for human-readability."""
        return "{\n\t%s\n}" % ",\n\t".join("%s: %s" % (k, v) for k, v in self.items())

    def __repr__(self) -> str:
        """Implement repr()."""
        kwargs = {k: v for k in self.__slots__[2:] if (v := getattr(self, k)) is not None}
        if kwargs:
            kwargs_str = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items()) + ", "
        else:
            kwargs_str = ""
        return f"{type(self).__name__}({kwargs_str}data={repr(self._data)})"

    def __sentry_repr__(self) -> str:
        """Override {}.__repr__() in Sentry."""
        return repr(self)

    def __eq__(self, other) -> bool:
        """Compare this object to another."""
        if self is other:
            return True

        if self.__class__ is not other.__class__:
            raise NotImplementedError(f"Cannot compare {self.__class__} and {other.__class__}")

        return self.data == other.data

    def __getstate__(self) -> dict[str, Any]:
        """Support pickle.dump()."""
        data = self.data
        return {
            "data": bytes(data) if not isinstance(data, (bytes, bytearray)) else data,
            **{attr: getattr(self, attr) for attr in self.__slots__[2:]},
        }

    def __setstate__(self, state: dict[str, Any]):
        """Support pickle.load()."""
        self.__init__(**state)

    def copy(self) -> "NumpyStruct":
        """Clone the instance."""
        return type(self)(self.data, **{attr: getattr(self, attr) for attr in self.__slots__[2:]})

    @staticmethod
    def _generate_get(
        name: str,
        type_: Union[str, np.dtype, list[Union[str, np.dtype]]],
    ) -> Callable[["NumpyStruct"], Any]:
        if _dtype_is_ascii(type_):
            type_ = str
        elif isinstance(type_, list):
            type_ = np.ndarray
        elif (char := np.dtype(type_).char) == "U":
            type_ = np.str_
        elif char == "S":
            type_ = np.bytes_
        elif char == "V":
            type_ = np.ndarray

        def get_field(self) -> Optional[type_]:
            if self._arr is None:
                self._arr = np.frombuffer(self.data, self.dtype, count=1)
            value = self._arr[name][0]
            if (nested_dtype := self.nested_dtypes.get(name)) is None:
                if value != value:
                    return None
                if type_ is str:
                    value = value.decode()
                if type_ in (str, np.str_):
                    value = value or None
                return value
            if (_dtype_is_ascii(nested_dtype) and (char := "S")) or (
                (char := nested_dtype.char) in ("S", "U") and nested_dtype.itemsize == 0
            ):
                offset, count, itemsize = value
                nested_dtype = f"{char}{itemsize}"
            else:
                offset, count = value
            return np.frombuffer(self.data, nested_dtype, offset=offset, count=count)

        get_field.__name__ = name
        return get_field


def _dtype_is_ascii(dtype: Union[str, np.dtype]) -> bool:
    return (dtype is ascii) or (isinstance(dtype, str) and dtype.startswith("ascii"))


def numpy_struct(cls):
    """
    Decorate a class to transform it to a NumpyStruct.

    The decorated class must define two sub-classes: `dtype` and `optional`.
    The former annotates numpy-friendly immutable fields. The latter annotates mutable fields.
    """
    dtype = cls.Immutable.__annotations__
    dtype_tuples = []
    nested_dtypes = {}
    for k, v in dtype.items():
        if isinstance(v, list):
            assert len(v) == 1, "Array must be specified as `[dtype]`."
            nested_dtype = v[0]
            if not (is_ascii := _dtype_is_ascii(nested_dtype)):
                nested_dtype = np.dtype(nested_dtype)
            nested_dtypes[k] = nested_dtype
            if is_ascii or (nested_dtype.char in ("S", "U") and nested_dtype.itemsize == 0):
                # save the characters count
                dtype_tuples.append((k, np.int32, 3))
            else:
                dtype_tuples.append((k, np.int32, 2))
        elif _dtype_is_ascii(v):
            dtype_tuples.append((k, "S" + v[6:-1]))
        else:
            dtype_tuples.append((k, v))
    try:
        optional = cls.Optional.__annotations__
    except AttributeError:
        optional = {}
    field_names = NamedTuple(
        f"{cls.__name__}FieldNames",
        [(k, str) for k in chain(dtype, optional)],
    )(*chain(dtype, optional))
    base = type(
        cls.__name__ + "Base",
        (NumpyStruct,),
        {k: property(NumpyStruct._generate_get(k, v)) for k, v in dtype.items()},
    )
    body = {
        "__slots__": ("_data", "_arr", *optional),
        "dtype": np.dtype(dtype_tuples),
        "nested_dtypes": nested_dtypes,
        "f": field_names,
    }
    struct_cls = type(cls.__name__, (cls, base), body)
    struct_cls.__module__ = cls.__module__
    cls.__name__ += "Origin"
    return struct_cls


@sentry_span
def df_from_structs(
    items: Iterable[NumpyStruct],
    length: Optional[int] = None,
) -> pd.DataFrame:
    """
    Combine several NumpyStruct-s to a Pandas DataFrame.

    :param items: A collection, a generator, an iterator - all are accepted.
    :param length: In case `items` does not support `len()`, specify the number of structs \
                   for better performance.
    :return: Pandas DataFrame with columns set to struct fields.
    """
    columns = {}
    try:
        if length is None:
            length = len(items)
    except TypeError:
        # slower branch without pre-allocation
        items_iter = iter(items)
        try:
            first_item = next(items_iter)
        except StopIteration:
            return pd.DataFrame()
        assert isinstance(first_item, NumpyStruct)
        dtype = first_item.dtype
        nested_fields = first_item.nested_dtypes
        coerced_datas = [first_item.coerced_data]
        for k, v in first_item.items():
            if k not in dtype.names or k in nested_fields:
                columns[k] = [v]
        for item in items_iter:
            coerced_datas.append(item.coerced_data)
            for k in columns:
                columns[k].append(getattr(item, k))
        table_array = np.frombuffer(b"".join(coerced_datas), dtype=dtype)
        del coerced_datas
    else:
        items_iter = iter(items)
        try:
            first_item = next(items_iter)
        except StopIteration:
            return pd.DataFrame()
        assert isinstance(first_item, NumpyStruct)
        dtype = first_item.dtype
        nested_fields = first_item.nested_dtypes
        itemsize = dtype.itemsize
        coerced_datas = bytearray(itemsize * length)
        coerced_datas[:itemsize] = first_item.coerced_data
        for k, v in first_item.items():
            if k not in dtype.names or k in nested_fields:
                columns[k] = column = [None] * length
                column[0] = v
        for i, item in enumerate(items_iter, 1):
            coerced_datas[i * itemsize : (i + 1) * itemsize] = item.coerced_data
            for k in columns:
                columns[k][i] = item[k]
        table_array = np.frombuffer(coerced_datas, dtype=dtype)
        del coerced_datas
    for field_name in dtype.names:
        if field_name not in nested_fields:
            columns[field_name] = table_array[field_name]
    del table_array
    column_types = {}
    try:
        for k, v in first_item.Optional.__annotations__.items():
            if not isinstance(v, type) or not issubclass(v, (datetime, np.datetime64, float)):
                # we can only unbox types that have a "NaN" value
                v = object
            column_types[k] = v
    except AttributeError:
        pass  # no Optional
    for k, v in columns.items():
        column_type = column_types.get(k, object)
        if issubclass(column_type, datetime):
            v = tslib.array_to_datetime(np.array(v, dtype=object), utc=True, errors="raise")[0]
        elif issubclass(column_type, timedelta):
            v = np.array(v, dtype="timedelta64[s]")
        elif np.dtype(column_type) != np.dtype(object):
            v = np.array(v, dtype=column_type)
        columns[k] = v
    df = pd.DataFrame.from_dict(columns)
    sentry_sdk.Hub.current.scope.span.description = str(len(df))
    return df


def dataclass_asdict(dataclass_obj: Any) -> Mapping[str, Any]:
    """Convert a dataclass instance to a dict.

    This is lighter than stdlib dataclasses.asdict since fields are not recursed and
    complex values are not deep-copied.
    Simply field name/value couples will be the values of the dict.
    Dataclass fields order is preserved in the returned dict.
    """
    return {f.name: getattr(dataclass_obj, f.name) for f in dataclasses.fields(dataclass_obj)}
