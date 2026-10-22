import { redirect } from "next/navigation";

// The admin app has no separate deals list — the dashboard grid is the list.
export default async function DealsIndex({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect(`/${locale}/dashboard`);
}
