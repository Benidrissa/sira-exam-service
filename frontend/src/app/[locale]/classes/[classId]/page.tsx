"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSchoolClass, enrollStudent, removeMember } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useParams } from "next/navigation";
import { toast } from "sonner";
import { formatError } from "@/lib/formatError";
import { BackLink } from "@/components/BackLink";
import { Skeleton } from "@/components/ui/skeleton";
import { usePaginatedList } from "@/hooks/usePaginatedList";
import { PaginationControls } from "@/components/PaginationControls";

type Member = { id: string; user_id: string };

function MemberList({ members, onRemove, removePending }: {
  members: Member[];
  onRemove: (uid: string) => void;
  removePending: boolean;
}) {
  const { page, total, totalPages, currentPage, setPage, filters, setFilter } =
    usePaginatedList<Member>(members, {
      pageSize: 20,
      filterFn: (m, f) => !f.search || m.user_id.includes(f.search),
    });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Members ({members.length})</CardTitle>
          {members.length > 5 && (
            <Input
              placeholder="Search by UUID…"
              value={filters.search}
              onChange={e => setFilter("search", e.target.value)}
              className="max-w-xs font-mono text-sm h-8"
            />
          )}
        </div>
      </CardHeader>
      <CardContent>
        {members.length === 0
          ? <p className="text-muted-foreground text-sm">No enrolled students.</p>
          : (
            <>
              {total === 0 && <p className="text-sm text-muted-foreground">No members match your search.</p>}
              <div className="space-y-2">
                {page.map(m => (
                  <div key={m.id} className="flex items-center justify-between py-2 border-b last:border-0">
                    <p className="font-mono text-sm">{m.user_id}</p>
                    <Button size="sm" variant="destructive" onClick={() => onRemove(m.user_id)} disabled={removePending}>
                      Remove
                    </Button>
                  </div>
                ))}
              </div>
              <PaginationControls currentPage={currentPage} totalPages={totalPages} totalItems={total} pageSize={20} onPageChange={setPage} />
            </>
          )
        }
      </CardContent>
    </Card>
  );
}

export default function ClassDetailPage() {
  const params = useParams();
  const classId = params.classId as string;
  const locale = params.locale as string;
  const qc = useQueryClient();
  const [userId, setUserId] = useState("");
  const [enrollError, setEnrollError] = useState<string | null>(null);

  const { data: cls, isLoading, error } = useQuery({
    queryKey: ["school-class", classId],
    queryFn: () => getSchoolClass(classId),
  });

  const enrollMutation = useMutation({
    mutationFn: () => enrollStudent(classId, userId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["school-class", classId] }); setUserId(""); setEnrollError(null); toast.success("Student enrolled"); },
    onError: (e) => { const msg = formatError(e); setEnrollError(msg); toast.error(msg); },
  });

  const removeMutation = useMutation({
    mutationFn: (uid: string) => removeMember(classId, uid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["school-class", classId] }); toast.success("Student removed"); },
    onError: (e) => toast.error(formatError(e)),
  });

  if (isLoading) return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-28 w-full rounded-xl" />
      <Skeleton className="h-36 w-full rounded-xl" />
    </main>
  );
  if (error || !cls) return <p className="p-8 text-destructive">{formatError(error)}</p>;

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-6">
      <BackLink href={`/${locale}/classes`} label="Classes" />
      <div>
        <h1 className="text-2xl font-bold">{cls.name}</h1>
        <Badge variant="outline">{cls.academic_year}</Badge>
      </div>

      {/* Enroll student */}
      <Card>
        <CardHeader><CardTitle>Enroll Student</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-3">
            <div className="flex-1 space-y-1">
              <Input placeholder="Student UUID (e.g. dddddddd-0000-…)" value={userId} onChange={e => setUserId(e.target.value)} className="font-mono text-sm" />
              <p className="text-xs text-muted-foreground">Paste the student&apos;s UUID from user management</p>
            </div>
            <Button onClick={() => enrollMutation.mutate()} disabled={!userId || enrollMutation.isPending} className="shrink-0">
              {enrollMutation.isPending ? "Enrolling…" : "Enroll"}
            </Button>
          </div>
          {enrollError && <p className="text-sm text-destructive">{enrollError}</p>}
        </CardContent>
      </Card>

      {/* Member list with search + pagination */}
      <MemberList
        members={cls.members ?? []}
        onRemove={(uid) => removeMutation.mutate(uid)}
        removePending={removeMutation.isPending}
      />
    </main>
  );
}
