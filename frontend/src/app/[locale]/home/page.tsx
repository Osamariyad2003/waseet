import { redirect } from "next/navigation";

export default async function HomeRedirect({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  redirect(`/${locale}/deals`);
}
