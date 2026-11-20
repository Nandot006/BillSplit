"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useCurrentUser } from "@/components/current-user";
import { Button, ButtonLink, Loading, Notice, PageHeader } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import {
  CORE_QUESTIONS,
  OPTIONAL_QUESTIONS,
  rephrase,
  SCALE_VALUES,
  toSubmission,
  unansweredCoreQuestions,
  type Answers,
  type Question,
} from "@/lib/questionnaire";
import { useResource } from "@/lib/use-resource";

export function QuestionnaireScreen({
  personId,
  nextPath,
}: {
  personId: string;
  nextPath: string | null;
}) {
  const router = useRouter();
  const user = useCurrentUser();
  const person = useResource(() => api.getPerson(personId), [personId], { refetchOnFocus: false });
  const [answers, setAnswers] = useState<Answers>({});
  const [showOptional, setShowOptional] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const done = nextPath ?? `/people/${personId}`;

  if (person.loading && !person.data) return <Loading />;
  if (!person.data)
    return <Notice tone="error">{person.error ?? "Couldn't load this person."}</Notice>;

  const isMe = person.data.supabase_user_id === user.id;
  const name = person.data.display_name;
  const remaining = unansweredCoreQuestions(answers).length;

  function set<K extends keyof Answers>(field: K, value: Answers[K]) {
    setAnswers((prev) => ({ ...prev, [field]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    let body;
    try {
      body = toSubmission(answers);
    } catch (e) {
      setError((e as Error).message);
      return;
    }
    setSaving(true);
    try {
      await api.submitQuestionnaire(personId, body);
      router.push(done);
    } catch (e) {
      setError(errorMessage(e));
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <PageHeader title={isMe ? "What do you usually order?" : `What does ${name} usually order?`}>
        <p className="text-ink-soft">
          {isMe ? "Your" : `${name}'s`} answers seed BillSplit&apos;s guesses about who had what.
          Dietary answers are treated as hard rules: a vegetarian is never given a chicken dish. It
          keeps learning from corrections, so rough answers are fine.
        </p>
      </PageHeader>

      <ol className="flex flex-col gap-6">
        {CORE_QUESTIONS.map((q, i) => (
          <QuestionRow
            key={q.field}
            number={i + 1}
            question={q}
            answers={answers}
            onAnswer={set}
            you={isMe}
            name={name}
          />
        ))}
      </ol>

      <div className="mt-8">
        {showOptional ? (
          <>
            <h2 className="mb-1 text-lg font-semibold">A few more, if you like</h2>
            <p className="mb-4 text-sm text-ink-soft">Skip any of these.</p>
            <ol className="flex flex-col gap-6" start={CORE_QUESTIONS.length + 1}>
              {OPTIONAL_QUESTIONS.map((q, i) => (
                <QuestionRow
                  key={q.field}
                  number={CORE_QUESTIONS.length + i + 1}
                  question={q}
                  answers={answers}
                  onAnswer={set}
                  you={isMe}
                  name={name}
                />
              ))}
            </ol>
          </>
        ) : (
          <Button type="button" variant="secondary" onClick={() => setShowOptional(true)}>
            Answer 5 more questions (optional)
          </Button>
        )}
      </div>

      <div className="sticky bottom-0 -mx-4 mt-8 flex flex-wrap items-center gap-3 border-t border-line bg-paper/95 px-4 py-4 backdrop-blur">
        <Button type="submit" busy={saving} disabled={remaining > 0}>
          Save answers
        </Button>
        <ButtonLink href={done} variant="quiet">
          Skip for now
        </ButtonLink>
        <span className="text-sm text-muted" aria-live="polite">
          {remaining > 0 ? `${remaining} question${remaining === 1 ? "" : "s"} left` : "All set"}
        </span>
        {error && (
          <div className="w-full">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
      </div>
    </form>
  );
}

function QuestionRow({
  number,
  question,
  answers,
  onAnswer,
  you,
  name,
}: {
  number: number;
  question: Question;
  answers: Answers;
  onAnswer: <K extends keyof Answers>(field: K, value: Answers[K]) => void;
  you: boolean;
  name: string;
}) {
  const prompt = you ? question.prompt : rephrase(question.prompt, name);
  const id = `q-${question.field}`;
  return (
    <li className="rounded-xl border border-line bg-surface p-4">
      <fieldset aria-describedby={"hint" in question && question.hint ? `${id}-hint` : undefined}>
        <legend className="mb-3 font-semibold">
          <span className="mr-2 text-muted">{number}.</span>
          {prompt}
        </legend>
        {"hint" in question && question.hint && (
          <p id={`${id}-hint`} className="-mt-2 mb-3 text-sm text-muted">
            {question.hint}
          </p>
        )}
        {question.kind === "diet" && (
          <Choices
            name={id}
            options={question.options.map((o) => ({ key: o.value, label: o.label }))}
            selected={answers.vegetarian_or_vegan}
            onSelect={(v) => onAnswer("vegetarian_or_vegan", v as Answers["vegetarian_or_vegan"])}
          />
        )}
        {question.kind === "yesno" && (
          <Choices
            name={id}
            options={[
              { key: "yes", label: "Yes" },
              { key: "no", label: "No" },
            ]}
            selected={
              answers[question.field] === undefined
                ? undefined
                : answers[question.field]
                  ? "yes"
                  : "no"
            }
            onSelect={(v) => onAnswer(question.field, v === "yes")}
          />
        )}
        {question.kind === "scale" && (
          <Choices
            name={id}
            options={question.steps.map((label, i) => ({ key: String(SCALE_VALUES[i]), label }))}
            selected={
              answers[question.field] === undefined ? undefined : String(answers[question.field])
            }
            onSelect={(v) => onAnswer(question.field, Number(v))}
            scale
          />
        )}
        {question.kind === "text" && (
          <textarea
            id={id}
            aria-label={prompt}
            value={answers.additional_preferences ?? ""}
            onChange={(e) => onAnswer("additional_preferences", e.target.value)}
            rows={3}
            className="w-full rounded-lg border border-line-strong bg-paper px-3 py-2 text-base"
            placeholder="e.g. Allergic to shellfish. Always gets a filter coffee."
          />
        )}
      </fieldset>
    </li>
  );
}

function Choices({
  name,
  options,
  selected,
  onSelect,
  scale = false,
}: {
  name: string;
  options: { key: string; label: string }[];
  selected: string | undefined;
  onSelect: (key: string) => void;
  scale?: boolean;
}) {
  return (
    <div className={scale ? "grid grid-cols-1 gap-2 sm:grid-cols-5" : "flex flex-wrap gap-2"}>
      {options.map((option) => {
        const checked = selected === option.key;
        return (
          <label
            key={option.key}
            className={`cursor-pointer rounded-lg border px-3 py-2 text-center text-sm transition has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-[var(--focus)] ${
              checked
                ? "border-ink bg-ink font-semibold text-paper"
                : "border-line-strong hover:border-ink"
            }`}
          >
            <input
              type="radio"
              name={name}
              value={option.key}
              checked={checked}
              onChange={() => onSelect(option.key)}
              className="sr-only"
            />
            {option.label}
          </label>
        );
      })}
    </div>
  );
}
