import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sira Exam Service",
  description: "AI-generated proctored exams for university accreditation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
