import ReviewEditor from "@/components/ReviewEditor";

export default async function RecordingPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ReviewEditor projectId={id} />;
}
