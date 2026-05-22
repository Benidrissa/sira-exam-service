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
import { Archive, ArchiveRestore, BookOpen } from "lucide-react";
import { toast } from "sonner";
import { formatError } from "@/lib/formatError";
import { Skeleton } from "@/components/ui/skeleton";

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
      setName(""); setYear(""); setCreateError(null);
      toast.success("Class created");
    },
    onError: (e) => { const msg = formatError(e); setCreateError(msg); toast.error(msg); },
  });

  const archiveMutation = useMutation({
    mutationFn: ({ classId, archive }: { classId: string; archive: boolean }) =>
      updateClass(classId, { archive }),
    onSuccess: (_r, { archive }) => { qc.invalidateQueries({ queryKey: ["school-classes"] }); toast.success(archive ? "Class archived" : "Class unarchived"); },
    onError: (e) => toast.error(formatError(e)),
  });

  if (isLoading) return (
    <main className="max-w-4xl mx-auto p-8 space-y-6">
      <Skeleton className="h-8 w-40" />
      {[1, 2, 3].map(i => <Skeleton key={i} className="h-16 w-full rounded-xl" />)}
    </main>
  );
  if (error) return <p className="p-8 text-destructive">{formatError(error)}</p>;

  return (
    <main className="max-w-4xl mx-auto p-8 space-y-6">
      <h1 className="text-2xl font-bold">Class Rosters</h1>

      {/* Create form — teacher only */}
      {isTeacher && (
        <Card>
          <CardHeader><CardTitle>Create Class</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-col sm:flex-row gap-3">
              <Input placeholder="Class name (e.g. L3 Info A)" value={name} onChange={e => setName(e.target.value)} />
              <Input placeholder="Academic year (e.g. 2025-2026)" value={year} onChange={e => setYear(e.target.value)} />
              <Button onClick={() => createMutation.mutate()} disabled={!name || !year || createMutation.isPending} className="shrink-0">
                {createMutation.isPending ? "Creating…" : "Create"}
              </Button>
            </div>
            {createError && <p className="text-sm text-destructive">{createError}</p>}
          </CardContent>
        </Card>
      )}

      {/* Class list */}
      <div className="space-y-3">
        {classes?.length === 0 && isTeacher && (
          <div className="py-12 text-center space-y-3">
            <BookOpen className="mx-auto h-10 w-10 text-muted-foreground" />
            <p className="font-medium">No classes yet</p>
            <p className="text-sm text-muted-foreground">Create your first class to assign exams to students</p>
          </div>
        )}
        {classes?.length === 0 && !isTeacher && <p className="text-muted-foreground">No classes found.</p>}
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

