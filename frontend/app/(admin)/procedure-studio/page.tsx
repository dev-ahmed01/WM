import { redirect } from 'next/navigation';

// The studio is a working editor, not a second dashboard made of links.
export default function ProcedureStudioHome() {
  redirect('/procedure-studio/drafts');
}
