"""Pagination helper with an off-by-one bug on the boundary."""

def next_page(items, page_index, page_size=10):
    if page_index < 0:
        raise ValueError("page_index must be >= 0")
    if page_size <= 0:
        raise ValueError("page_size must be > 0")
    # BUG: off-by-one — this excludes the last item of the page
    start = page_index * page_size
    end = (page_index + 1) * page_size - 1
    return items[start:end]
