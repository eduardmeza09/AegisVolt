export type Paint = "blue" | "grey" | "black";

const ALT: Record<Paint, string> = {
  blue: "Vehículo eléctrico azul con luces cian encendidas",
  grey: "Vehículo eléctrico gris apagado",
  black: "Vehículo eléctrico negro con luces cian encendidas",
};

/** Foto del vehículo (public/img/car-<paint>.webp, fondo negro difuminado por máscara CSS). */
export function CarPhoto({ paint, className = "", flip = false, sizes = "(max-width: 680px) 100vw, 50vw", eager = false }: {
  paint: Paint;
  className?: string;
  flip?: boolean;
  sizes?: string;
  eager?: boolean;
}) {
  const base = `./img/car-${paint}`;
  return (
    <img
      className={`car-photo ${flip ? "flip" : ""} ${className}`}
      src={`${base}.webp`}
      srcSet={`${base}-sm.webp 900w, ${base}.webp 1800w`}
      sizes={sizes}
      width={1800}
      height={766}
      alt={ALT[paint]}
      loading={eager ? "eager" : "lazy"}
      decoding="async"
    />
  );
}
