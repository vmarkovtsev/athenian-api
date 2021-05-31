# cython: language_level=3, boundscheck=False, nonecheck=False, optimize.unpack_method_calls=True
# cython: warn.undeclared=True, warn.maybe_uninitialized=True
# distutils: language = c++

cimport cython
from libc.stdint cimport int64_t, uint64_t
from libcpp.set cimport set
import numpy as np

# __builtin_clzl is a compiler built-in that counts the number of leading zeros
cdef extern int __builtin_clzl(unsigned long)


def calculate_interval_intersections(starts: np.ndarray,
                                     finishes: np.ndarray,
                                     borders: np.ndarray,
                                     ) -> np.ndarray:
    cdef unsigned long max_intervals, groups_count
    assert len(starts) == len(finishes)
    assert starts.dtype == np.uint64
    assert finishes.dtype == np.uint64
    time_offset = starts.min()
    # require less bits for the timestamps
    starts -= time_offset
    finishes -= time_offset
    # there can be intervals of zero length, make them 1-second
    finishes[starts == finishes] += 1
    group_lengths = np.diff(borders, prepend=0)
    max_intervals = group_lengths.max()
    series = np.arange(max_intervals, dtype=np.uint64)
    intervals = np.concatenate([starts, finishes])
    size = len(starts)
    time_offset = 64 - __builtin_clzl(max_intervals - 1)
    intervals <<= time_offset
    groups_count = len(borders)
    group_offset = __builtin_clzl(groups_count - 1)
    group_indexes = np.repeat(np.arange(groups_count, dtype=np.uint64), group_lengths)
    intervals[:size] |= group_indexes << group_offset
    intervals[size:] |= group_indexes << group_offset
    # https://codereview.stackexchange.com/questions/83018/vectorized-numpy-version-of-arange-with-multiple-start-stop
    indexes = (
        np.repeat(group_lengths - group_lengths.cumsum(), group_lengths) +
        np.arange(group_lengths.sum())
    ).view(np.uint64)
    intervals[:size] |= indexes
    intervals[size:] |= indexes
    # bits 0..time_offset - interval indexes, each in range 0..group length
    # bits time_offset..(64 - group_offset) - timestamps
    # bits (64 - group_offset)..63 - group index
    # stable sort because starts must come before finishes if the timestamps are equal
    intervals = np.sort(intervals, kind="stable")
    # remove the group indexes
    intervals &= (1 << group_offset) - 1
    raw = np.zeros(size, dtype=np.uint64)
    _calculate_interval_intersections(intervals, borders * 2, time_offset, raw)
    result = raw.astype(float) / (finishes - starts)
    return result


@cython.boundscheck(False)
@cython.wraparound(False)
cdef void _calculate_interval_intersections(const uint64_t[:] intervals,
                                            const int64_t[:] borders,
                                            char time_offset,
                                            uint64_t[:] intersections) nogil:
    cdef int64_t i, j, border_index, group_start, group_finish, ii_open, intersections_offset
    cdef uint64_t item, index_mask, timestamp, previous_timestamp, delta
    # set faster than unordered_set because we iterate over all elements on each step
    cdef set[int64_t] open_intervals
    cdef set[int64_t].iterator ii
    index_mask = (1 << time_offset) - 1
    previous_timestamp = 0  # not really needed but removes the warning
    for border_index in range(len(borders)):
        group_start = borders[border_index - 1] if border_index > 0 else 0
        intersections_offset = group_start >> 1
        group_finish = borders[border_index]
        for i in range(group_start, group_finish):
            item = intervals[i]
            timestamp = item >> time_offset
            delta = (timestamp - previous_timestamp) * open_intervals.size()
            for ii_open in open_intervals:
                intersections[intersections_offset + ii_open] += delta
            interval_index = item & index_mask
            ii = open_intervals.find(interval_index)
            if ii == open_intervals.end():
                open_intervals.insert(interval_index)
            else:
                open_intervals.erase(ii)
            previous_timestamp = timestamp
        open_intervals.clear()
