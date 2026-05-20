"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createSchoolClass, listSchoolClasses, updateClass } from "@/lib/api";
import type { SchoolClass } from "@/types/exam";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Archive, ArchiveRestore } from "lucide-react";

function getRoleFromCookie(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|; )access_token=([^;]*)/);
  if (!match) return null;
  try {
    const payload = JSON.parse(atob(decodeURIComponent(match[1]).split(".")[1]));
    return payload.role ?? null;
  } catch { return null; }
}

export default function ClassesPage() {
  const params = useParams();
  const locale = params.locale as string;
  const isTeacher = ["expert", "admin", "sub_admin"].includes(getRoleFromCookie() ?? "");
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [year, setYear] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  const { data: classes, isLoading, error } = useQuery({
    queryKey: ["school-classes"],
    queryFn: () => listSchoolClasses(),
  });

  const createMutation = useMutation({
    mutationFn: () => createSchoolClass({ name, academic_year: year }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["school-classes"] });
      setName("");
      setYear("");
      setCreateError(null);
    },
    onError: (e) => setCreateError(String(e)),
  });

  const archiveMutation = useMutation({
    mutationFn: ({ classId, archive }: { classId: string; archive: boolean }) =>
      updateClass(classId, { archive }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["school-classes"] }),
  });

  if (isLoading) return <div className="p-8">Loading…</div>;
  if (error) return <p className="p-8 text-destructive">{String(error)}</p>;

  return (
    <main className="max-w-4xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-bold">Class Rosters</h1>

      {/* Create form — teacher only */}
      {isTeacher && (
        <Card>
          <CardHeader><CardTitle>Create Class</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-3">
              <Input placeholder="Class name (e.g. L3 Info A)" value={name} onChange={e => setName(e.target.value)} />
              <Input placeholder="Year (e.g. 2025-2026)" value={year} onChange={e => setYear(e.target.value)} />
              <Button onClick={() => createMutation.mutate()} disabled={!name || !year || createMutation.isPending}>
                {createMutation.isPending ? "Creating…" : "Create"}
              </Button>
            </div>
            {createError && <p className="text-sm text-destructive">{createError}</p>}
          </CardContent>
        </Card>
      )}

      {/* Class list */}
      <div className="space-y-3">
        {classes?.length === 0 && <p className="text-muted-foreground">No classes yet.</p>}
        {classes?.map((c: SchoolClass) => (
          <Card key={c.id} className={c.archived_at ? "opacity-60" : ""}>
            <CardContent className="flex items-center justify-between py-4">
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-semibold">{c.name}</p>
                  {c.archived_at && (
                    <Badge variant="secondary" className="text-xs">Archived</Badge>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">{c.academic_year}</p>
              </div>
              <div className="flex items-center gap-2">
                {isTeacher && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => archiveMutation.mutate({ classId: c.id, archive: !c.archived_at })}
                    disabled={archiveMutation.isPending}
                    title={c.archived_at ? "Unarchive" : "Archive"}
                  >
                    {c.archived_at
                      ? <ArchiveRestore className="h-4 w-4" />
                      : <Archive className="h-4 w-4" />}
                  </Button>
                )}
                <Link href={`/${locale}/classes/${c.id}`}>
                  <Button variant="outline" size="sm">Manage →</Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}

