import { useState, useMemo, useEffect } from "react";

export interface FilterState {
  search: string;
  status: string;
  [key: string]: string;
}

interface UsePaginatedListOptions<T> {
  pageSize: number;
  filterFn: (item: T, filters: FilterState) => boolean;
}

function useValueDebounce(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export function usePaginatedList<T>(
  items: T[],
  { pageSize, filterFn }: UsePaginatedListOptions<T>,
) {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<FilterState>({ search: "", status: "" });
  const debouncedSearch = useValueDebounce(filters.search, 300);

  const effectiveFilters: FilterState = { ...filters, search: debouncedSearch };

  const filtered = useMemo(
    () => items.filter((item) => filterFn(item, effectiveFilters)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, debouncedSearch, JSON.stringify(Object.fromEntries(
      Object.entries(filters).filter(([k]) => k !== "search")
    ))],
  );

  // Reset to page 1 whenever any filter changes (includes extra keys beyond search/status)
  useEffect(() => { setPage(1); }, [JSON.stringify(effectiveFilters)]); // eslint-disable-line react-hooks/exhaustive-deps

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const slice = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  function setFilter(key: string, value: string) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  return {
    page: slice,
    allFiltered: filtered,
    total: filtered.length,
    totalPages,
    currentPage: safePage,
    setPage,
    filters,
    setFilter,
  };
}
