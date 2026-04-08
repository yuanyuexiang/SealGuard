import Image from "next/image";

export default function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "brand-mark compact" : "brand-mark"}>
      <div className={compact ? "brand-logo-frame compact" : "brand-logo-frame"}>
        <Image
          src="/fQMAGJ7Wp.jpeg"
          alt="Coca-Cola logo"
          fill
          className="brand-logo-image"
          priority
        />
      </div>
    </div>
  );
}
