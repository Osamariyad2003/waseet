import Link from "next/link";

export default function NotFound() {
  return (
    <html lang="en">
      <body className="flex min-h-dvh items-center justify-center p-6">
        <div className="text-center">
          <p className="text-sm text-neutral-500">That page does not exist.</p>
          <Link href="/en/deals" className="mt-2 inline-block text-sm underline">
            Go to your deals
          </Link>
        </div>
      </body>
    </html>
  );
}
