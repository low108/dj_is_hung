import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "The Garden",
  description: "AI twins date in the Garden until two of them cross the wall together.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
