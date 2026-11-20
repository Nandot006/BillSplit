import { QuestionnaireScreen } from "./questionnaire-screen";

export default async function QuestionnairePage(
  props: PageProps<"/people/[personId]/questionnaire">,
) {
  const { personId } = await props.params;
  const { next } = await props.searchParams;
  const nextPath =
    typeof next === "string" && next.startsWith("/") && !next.startsWith("//") ? next : null;
  return <QuestionnaireScreen personId={personId} nextPath={nextPath} />;
}
