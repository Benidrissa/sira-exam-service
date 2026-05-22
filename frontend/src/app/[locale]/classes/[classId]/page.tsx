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
          <div className="flex gap-3">
            <Input placeholder="Student user ID (UUID)" value={userId} onChange={e => setUserId(e.target.value)} className="font-mono text-sm" />
            <Button onClick={() => enrollMutation.mutate()} disabled={!userId || enrollMutation.isPending}>
              {enrollMutation.isPending ? "Enrolling…" : "Enroll"}
            </Button>
          </div>
          {enrollError && <p className="text-sm text-destructive">{enrollError}</p>}
        </CardContent>
      </Card>

      {/* Member list */}
      <Card>
        <CardHeader><CardTitle>Members ({cls.members?.length ?? 0})</CardTitle></CardHeader>
        <CardContent>
          {cls.members?.length === 0
            ? <p className="text-muted-foreground text-sm">No enrolled students.</p>
            : <div className="space-y-2">
                {cls.members?.map(m => (
                  <div key={m.id} className="flex items-center justify-between py-2 border-b last:border-0">
                    <p className="font-mono text-sm">{m.user_id}</p>
                    <Button size="sm" variant="destructive" onClick={() => removeMutation.mutate(m.user_id)} disabled={removeMutation.isPending}>
                      Remove
                    </Button>
                  </div>
                ))}
              </div>
          }
        </CardContent>
      </Card>
    </main>
  );
}
