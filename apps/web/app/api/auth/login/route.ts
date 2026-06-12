import { NextResponse } from "next/server";

import { APIException, loginClinician } from "../../../../lib/api";
import { setSessionCookies } from "../../../../lib/auth";

export async function POST(req: Request) {
  let payload: { email?: string; password?: string; role?: string };
  try {
    payload = (await req.json()) as typeof payload;
  } catch {
    return NextResponse.json({ ok: false, code: "INVALID_BODY" }, { status: 400 });
  }
  const { email, password, role } = payload;
  if (!email || !password || (role !== "clinician" && role !== "org_admin")) {
    return NextResponse.json({ ok: false, code: "INVALID_INPUT" }, { status: 400 });
  }
  try {
    const pair = await loginClinician(email, password, role);
    await setSessionCookies({
      accessToken: pair.accessToken,
      refreshToken: pair.refreshToken,
      user: { userId: pair.userId, role: pair.role, email },
      expiresInSec: pair.expiresIn,
    });
    return NextResponse.json({ ok: true });
  } catch (e) {
    if (e instanceof APIException) {
      return NextResponse.json(
        { ok: false, code: e.body.code },
        { status: e.status },
      );
    }
    return NextResponse.json({ ok: false, code: "NETWORK" }, { status: 502 });
  }
}
