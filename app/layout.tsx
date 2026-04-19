import type { Metadata } from "next";
import { AppChrome } from "./app-chrome";
import "./globals.css";

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
    <html lang="en">
      <body className="appBody">
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  );
}
