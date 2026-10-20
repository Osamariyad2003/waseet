"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import type { DeliverableType } from "@/lib/types";

const DELIVERABLE_TYPES: DeliverableType[] = ["url", "repo", "image", "file", "text"];

const schema = z.object({
  type: z.enum(["url", "file", "image", "repo", "text"]),
  content_ref: z.string().trim().min(1),
  note: z.string().trim().max(2000).optional(),
});

type FormValues = z.infer<typeof schema>;

interface DeliverableUploaderProps {
  onSubmit: (values: {
    type: DeliverableType;
    content_ref: string;
    note?: string | null;
  }) => Promise<void>;
  isSubmitting?: boolean;
  error?: string;
}

/**
 * The seller's submission form.
 *
 * "Uploader" is the brief's name for it; what it actually collects is a
 * reference — a link, a repo, or text. Binary upload is not in the SRS
 * scope, and the backend stores a `content_ref`, so offering a file picker
 * that silently could not upload would be worse than not offering one.
 * `file` and `image` remain selectable because the backend's enum has them
 * and a seller may be pasting a link to either.
 */
export function DeliverableUploader({
  onSubmit,
  isSubmitting,
  error,
}: DeliverableUploaderProps) {
  const t = useTranslations();

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { type: "url", content_ref: "", note: "" },
  });

  const type = watch("type");
  const isFreeText = type === "text";

  return (
    <form
      onSubmit={handleSubmit(async (values) =>
        onSubmit({
          type: values.type,
          content_ref: values.content_ref,
          note: values.note?.trim() ? values.note.trim() : null,
        }),
      )}
      className="space-y-4"
      noValidate
    >
      <Field label={t("deliverable.type")}>
        {(props) => (
          <Select {...props} {...register("type")}>
            {DELIVERABLE_TYPES.map((option) => (
              <option key={option} value={option}>
                {t(`deliverable.types.${option}`)}
              </option>
            ))}
          </Select>
        )}
      </Field>

      <Field
        label={t("deliverable.content")}
        error={errors.content_ref ? t("validation.contentRequired") : undefined}
      >
        {(props) =>
          isFreeText ? (
            <Textarea
              {...props}
              {...register("content_ref")}
              placeholder={t("deliverable.contentPlaceholderText")}
              rows={5}
            />
          ) : (
            <Input
              {...props}
              {...register("content_ref")}
              inputMode="url"
              placeholder={t("deliverable.contentPlaceholderUrl")}
            />
          )
        }
      </Field>

      <Field label={t("deliverable.note")}>
        {(props) => <Textarea {...props} {...register("note")} rows={2} />}
      </Field>

      {error ? (
        <p role="alert" className="text-sm text-status-attention">
          {error}
        </p>
      ) : null}

      <Button type="submit" disabled={isSubmitting} size="lg">
        {isSubmitting ? (
          <>
            <Spinner label={t("deliverable.submitting")} />
            {t("deliverable.submitting")}
          </>
        ) : (
          t("deliverable.submit")
        )}
      </Button>
    </form>
  );
}
