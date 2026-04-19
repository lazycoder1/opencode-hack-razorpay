import type { Metadata } from "next";
import { Inter, Inter_Tight } from "next/font/google";
import { AppChrome } from "./app-chrome";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

const interTight = Inter_Tight({
  variable: "--font-inter-tight",
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Microsite Studio",
  description: "Editorial batch microsite generation with live observability.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${interTight.variable}`}>
      <body className="appBody">
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  );
}
