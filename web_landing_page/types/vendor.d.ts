declare module 'jos-animation' {
  interface JOSOptions {
    passive?: boolean;
    once?: boolean;
    animation?: string;
    timingFunction?: string;
    threshold?: number;
    delay?: number;
    duration?: number;
    scrollDirection?: string;
    rootMargin?: string;
  }
  const JOS: {
    init: (options?: JOSOptions) => void;
    refresh: () => void;
  };
  export default JOS;
}

declare module 'fslightbox-react';

declare module 'react-router-dom' {
  export function useLocation(): { pathname: string };
}

declare module '*.png' {
  const content: import('next/image').StaticImageData;
  export default content;
}

declare module '*.jpg' {
  const content: import('next/image').StaticImageData;
  export default content;
}

declare module '*.svg' {
  const content: import('next/image').StaticImageData;
  export default content;
}
