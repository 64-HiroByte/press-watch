import type { SVGProps } from "react";

export function MockRetrievalFailureDecoration(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round"
      {...props}
    >
      <rect x="7" y="3" width="8" height="12" rx="2" />
      <path d="M15 6h6M15 12h6" />
      <path d="M7 9H6a3 3 0 0 0-3 3v9" />
    </svg>
  );
}
