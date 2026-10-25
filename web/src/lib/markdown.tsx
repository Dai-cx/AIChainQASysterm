// Extracted from App.tsx during the P7b module split.
import type { ReactNode } from "react";

export function renderAnswerMarkdown(markdown: string): ReactNode[] {
  return markdown.split(/\r?\n/).map((line, index) => {
    const text = line.trim();
    if (!text) return <div className="answer-space" key={index} />;
    if (text.startsWith("### ")) {
      return <h3 key={index}>{renderInlineMarkdown(text.slice(4))}</h3>;
    }
    if (text.startsWith("## ")) {
      return <h3 key={index}>{renderInlineMarkdown(text.slice(3))}</h3>;
    }
    const bulletMatch = text.match(/^[-*]\s+(.+)$/);
    if (bulletMatch) {
      return (
        <p className="answer-bullet" key={index}>
          <span>•</span>
          <span>{renderInlineMarkdown(bulletMatch[1])}</span>
        </p>
      );
    }
    const orderedMatch = text.match(/^(\d+)\.\s+(.+)$/);
    if (orderedMatch) {
      return (
        <p className="answer-bullet" key={index}>
          <span>{orderedMatch[1]}.</span>
          <span>{renderInlineMarkdown(orderedMatch[2])}</span>
        </p>
      );
    }
    return <p key={index}>{renderInlineMarkdown(text)}</p>;
  });
}

export function renderInlineMarkdown(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <span key={index}>{part}</span>;
  });
}
