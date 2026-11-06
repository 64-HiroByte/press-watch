import { createHash, timingSafeEqual } from "node:crypto";
import { type NextRequest, NextResponse } from "next/server";

const cacheControl = "private, no-store";

export function proxy(request: NextRequest) {
  if (process.env.NODE_ENV !== "production") return NextResponse.next();

  const user = process.env.PRESSWATCH_BASIC_AUTH_USER;
  const password = process.env.PRESSWATCH_BASIC_AUTH_PASSWORD;
  const headers = { "Cache-Control": cacheControl };
  if (!user?.trim() || user.includes(":") || !password?.trim()) {
    return new NextResponse("Service Unavailable", { status: 503, headers });
  }

  if (request.nextUrl.pathname === "/health") return new NextResponse("ok\n", { headers });

  const presented = request.headers.get("authorization")?.match(/^Basic +(\S+)$/i)?.[1];
  const expected = Buffer.from(`${user}:${password}`, "utf8").toString("base64");
  if (
    !presented ||
    !timingSafeEqual(
      createHash("sha256").update(presented).digest(),
      createHash("sha256").update(expected).digest(),
    )
  ) {
    return new NextResponse("Unauthorized", {
      status: 401,
      headers: { ...headers, "WWW-Authenticate": 'Basic realm="PressWatch", charset="UTF-8"' },
    });
  }

  const response = NextResponse.next();
  response.headers.set("Cache-Control", cacheControl);
  return response;
}
