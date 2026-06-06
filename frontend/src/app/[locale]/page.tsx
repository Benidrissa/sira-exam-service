"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { listExamBanks, listBankTests, listStudentTests } from "@/lib/api";
import type { ExamBank, BankStatus, StudentTestSummary } from "@/types/exam";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { cn } from "@/lib/utils";
import {
  Plus,
  GraduationCap,
  FileText,
  AlertCircle,
  CheckCircle,
  ClipboardList,
  Clock,
} from "lucide-react";
import { usePaginatedList } from "@/hooks/usePaginatedList";
import { PaginationControls } from "@/components/PaginationControls";
import { Select } from "@/components/ui/select";
import type { ExamBank as ExamBankType } from "@/types/exam";

/* ── helpers ────────────────────────────────────────────────── */

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

function getRole(): string | null {
  const token = getCookie("access_token");
  if (!token) return null;
  try {
    return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")))?.role ?? null;
  } catch {
    return null;
  }
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const d = Math.floor(diff / 86400000);
  const h = Math.floor(diff / 3600000);
  const m = Math.floor(diff / 60000);
  if (d > 0) return `il y a ${d} j`;
  if (h > 0) return `il y a ${h} h`;
  if (m > 0) return `il y a ${m} min`;
  return "à l'instant";
}

const STATUS_BADGE_VARIANT: Record<BankStatus, "secondary" | "warning" | "success" | "outline"> = {
  draft: "secondary",
  generating: "warning",
  review: "warning",
  published: "success",
  archived: "outline",
};

const STATUS_LABEL_FR: Record<BankStatus, string> = {
  draft: "Brouillon",
  generating: "Génération",
  review: "Révision",
  published: "Publié",
  archived: "Archivé",
};

/* ── teacher view ───────────────────────────────────────────── */

function TeacherDashboard({ locale }: { locale: string }) {
  const { data: banks, isLoading, error, refetch } = useQuery({
    queryKey: ["banks"],
    queryFn: listExamBanks,
  });

  // Hook must be called unconditionally before any conditional returns
  const allBanks = banks ?? [];
  const { page, total, totalPages, currentPage, setPage, filters, setFilter } =
    usePaginatedList<ExamBankType>(allBanks, {
      pageSize: 10,
      filterFn: (b, f) => {
        const matchSearch = !f.search || b.title_fr.toLowerCase().includes(f.search.toLowerCase());
        const matchStatus = !f.status || b.status === f.status;
        return matchSearch && matchStatus;
      },
    });

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-muted" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Échec du chargement des banques d&apos;examens</AlertTitle>
        <AlertDescription className="mt-2 flex flex-col gap-2">
          <span>{String(error)}</span>
          <Button
            variant="outline"
            size="sm"
            className="w-fit border-destructive/40 text-destructive hover:bg-destructive/10"
            onClick={() => refetch()}
          >
            Réessayer
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page heading */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Mes banques d&apos;examens</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">{allBanks.length} banque{allBanks.length !== 1 ? "s" : ""} au total</p>
        </div>
        <Button asChild variant="default">
          <Link href={`/${locale}/create`}>
            <Plus />
            Nouvel examen
          </Link>
        </Button>
      </div>

      {/* Filter bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        <Input
          placeholder="Rechercher par titre…"
          value={filters.search}
          onChange={(e) => setFilter("search", e.target.value)}
          className="max-w-xs"
        />
        <Select
          options={[
            { value: "draft", label: "Brouillon" },
            { value: "generating", label: "Génération" },
            { value: "review", label: "Révision" },
            { value: "published", label: "Publié" },
            { value: "archived", label: "Archivé" },
          ]}
          placeholder="Tous les statuts"
          value={filters.status}
          onChange={(e) => setFilter("status", e.target.value)}
          className="w-44"
        />
      </div>

      {/* Empty state */}
      {allBanks.length === 0 && (
        <Card className="border-2 border-dashed border-border bg-transparent shadow-none py-12">
          <CardContent className="flex flex-col items-center gap-4 text-center pt-0">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
              <FileText className="h-7 w-7 text-muted-foreground" />
            </div>
            <div>
              <h3 className="text-base font-semibold">Aucune banque d&apos;examens</h3>
              <p className="mt-1 text-sm text-muted-foreground">Créez votre première banque d&apos;examens pour commencer</p>
            </div>
            <Button asChild variant="default">
              <Link href={`/${locale}/create`}><Plus />Nouvel examen</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {allBanks.length > 0 && total === 0 && (
        <p className="text-sm text-muted-foreground">Aucune banque ne correspond à vos filtres.</p>
      )}

      {/* Paginated list */}
      {page.length > 0 && (
        <div className="space-y-3">
          {page.map((bank) => (
            <BankCard key={bank.id} bank={bank} locale={locale} />
          ))}
        </div>
      )}

      <PaginationControls currentPage={currentPage} totalPages={totalPages} totalItems={total} pageSize={10} onPageChange={setPage} />
    </div>
  );
}

function BankCard({ bank, locale }: { bank: ExamBank; locale: string }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);

  // Pre-fetch the first published test for this bank (needed for Grading link + student link)
  const { data: tests } = useQuery({
    queryKey: ["bank-tests", bank.id],
    queryFn: () => listBankTests(bank.id),
    enabled: bank.status === "published",
    staleTime: 60_000,
  });
  const testId = tests?.[0]?.id ?? null;

  async function copyTestLink() {
    setCopyError(null);
    try {
      if (!testId) throw new Error("Aucun test trouvé pour cette banque");
      const url = `${window.location.origin}/${locale}/exams/${testId}/play`;
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch (e) {
      setCopyError(e instanceof Error ? e.message : "Impossible de copier le lien");
      setTimeout(() => setCopyError(null), 3000);
    }
  }

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-3">
          <CardTitle className="truncate max-w-xs text-base">{bank.title_fr}</CardTitle>
          <Badge
            variant={STATUS_BADGE_VARIANT[bank.status]}
            className={cn(
              bank.status === "generating" && "animate-pulse"
            )}
          >
            {STATUS_LABEL_FR[bank.status]}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          {bank.subject && <span>{bank.subject} · </span>}
          Updated {timeAgo(bank.updated_at)}
        </p>
      </CardHeader>

      <CardContent className="pt-1">
        {/* Generating shimmer */}
        {bank.status === "generating" && (
          <div className="flex items-center gap-2 rounded-lg bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
            <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
            Génération des questions…
          </div>
        )}

        {/* Actions */}
        {bank.status !== "generating" && (
          <div className="flex flex-wrap items-center gap-2">
            {(bank.status === "review" || bank.status === "published") && (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/${locale}/banks/${bank.id}/review`}>
                  Tableau de révision
                </Link>
              </Button>
            )}
            {bank.status === "published" && (
              <>
                <Button variant="outline" size="sm" asChild disabled={!testId}>
                  <Link href={testId ? `/${locale}/exams/${testId}/submissions` : "#"}>
                    Copies
                  </Link>
                </Button>
                <Button variant="outline" size="sm" asChild disabled={!testId}>
                  <Link href={testId ? `/${locale}/exams/${testId}/assignments` : "#"}>
                    Planifier
                  </Link>
                </Button>
                <Button variant="outline" size="sm" asChild disabled={!testId}>
                  <Link href={testId ? `/${locale}/exams/${testId}/results` : "#"}>
                    Notation
                  </Link>
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={copyTestLink}
                  className={cn(
                    copied &&
                      "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100",
                    copyError &&
                      "border-destructive/40 bg-destructive/5 text-destructive"
                  )}
                >
                  {copied ? (
                    <>
                      <CheckCircle className="h-3.5 w-3.5" />
                      Copié
                    </>
                  ) : (
                    "Copier le lien étudiant"
                  )}
                </Button>
                {copyError && (
                  <p className="text-xs text-destructive">{copyError}</p>
                )}
              </>
            )}
            {bank.status === "draft" && (
              <Button variant="outline" size="sm" asChild>
                <Link href={`/${locale}/create`}>Terminer la configuration</Link>
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ── student view ───────────────────────────────────────────── */

function StudentDashboard({ locale }: { locale: string }) {
  const { data: exams, isLoading } = useQuery({
    queryKey: ["student-tests"],
    queryFn: listStudentTests,
  });

  return (
    <div className="flex justify-center mt-16">
      <div className="w-full max-w-lg mx-auto space-y-4">
        <h1 className="text-xl font-bold text-center flex items-center justify-center gap-2">
          <GraduationCap className="h-5 w-5" />
          Mes examens planifiés
        </h1>

        {isLoading && (
          <p className="text-center text-muted-foreground text-sm">Chargement…</p>
        )}

        {!isLoading && (!exams || exams.length === 0) && (
          <Card>
            <CardContent className="py-10 text-center text-muted-foreground text-sm">
              Aucun examen n&apos;est actuellement planifié pour vos classes.
            </CardContent>
          </Card>
        )}

        {exams?.map((exam) => (
          <ExamScheduleCard key={exam.test_id} exam={exam} locale={locale} />
        ))}

        <Button variant="outline" size="sm" className="w-full" asChild>
          <Link href={`/${locale}/students/me/attempts`}>
            <ClipboardList className="h-3.5 w-3.5 mr-1" />
            Mon historique d&apos;examens
          </Link>
        </Button>
      </div>
    </div>
  );
}

function ExamScheduleCard({ exam, locale }: { exam: StudentTestSummary; locale: string }) {
  const closes = new Date(exam.closes_at);
  const quarterLabel = exam.quarter?.toUpperCase() ?? "—";

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">{exam.test_title}</CardTitle>
        <p className="text-sm text-muted-foreground">
          {exam.bank_subject && `${exam.bank_subject} · `}{exam.class_name} · {exam.academic_year} · {quarterLabel}
        </p>
      </CardHeader>
      <CardContent className="flex items-center justify-between gap-4">
        <p className="text-xs text-muted-foreground flex items-center gap-1">
          <Clock className="h-3 w-3" />
          Clôture le {closes.toLocaleString()}
        </p>
        {exam.has_attempted ? (
          <Button size="sm" variant="outline" asChild>
            <Link href={exam.attempt_id ? `/${locale}/attempts/${exam.attempt_id}/review` : "#"}>
              Voir les résultats
            </Link>
          </Button>
        ) : (
          <Button size="sm" asChild>
            <Link href={`/${locale}/exams/${exam.test_id}/play`}>
              Commencer l&apos;examen
            </Link>
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

/* ── main ───────────────────────────────────────────────────── */

export default function HomePage() {
  const params = useParams<{ locale?: string }>();
  const locale = params?.locale ?? "fr";

  // Synchronous role detection — no spinner flash
  const role = typeof window !== "undefined" ? getRole() : null;
  const isTeacher = role === "expert" || role === "admin" || role === "sub_admin";

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      {isTeacher ? (
        <TeacherDashboard locale={locale} />
      ) : (
        <StudentDashboard locale={locale} />
      )}
    </main>
  );
}
