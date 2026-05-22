import { useState, useMemo, useEffect } from "react";
import { useDebounce } from "@/hooks/use-debounce";

export interface FilterState {
  search: string;
  status: string;
  [key: string]: string;
}

interface UsePaginatedListOptions<T> {
  pageSize: number;
  filterFn: (item: T, filters: FilterState) => boolean;
}

export function usePaginatedList<T>(
  items: T[],
  { pageSize, filterFn }: UsePaginatedListOptions<T>,
) {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<FilterState>({ search: "", status: "" });
  const debouncedSearch = useDebounce(filters.search, 300);

  const effectiveFilters = { ...filters, search: debouncedSearch };

  const filtered = useMemo(
    () => items.filter((item) => filterFn(item, effectiveFilters)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, debouncedSearch, filters.status, ...Object.values(filters).filter((_, i) => i > 1)],
  );

  // Reset to page 1 when filter changes
  useEffect(() => { setPage(1); }, [debouncedSearch, filters.status]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const slice = filtered.slice((safePage - 1) * pageSize, safePage * pageSize);

  function setFilter(key: keyof FilterState, value: string) {
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
