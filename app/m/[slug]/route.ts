import { NextRequest, NextResponse } from "next/server";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;

  try {
    const response = await fetch(`${apiBaseUrl}/m/${slug}`, {
      cache: "no-store",
    });

    if (!response.ok) {
      return new NextResponse("Microsite not found", { status: 404 });
    }

    const html = await response.text();

    return new NextResponse(html, {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "public, max-age=60",
      },
    });
  } catch {
    return new NextResponse("Unable to load microsite", { status: 502 });
  }
}
