/** @type {import('tailwindcss').Config} */

const cssVar =
  (name) =>
  ({ opacityValue }) =>
    opacityValue === undefined
      ? `rgb(var(${name}))`
      : `rgb(var(${name}) / ${opacityValue})`;

const scale = (name) =>
  Object.fromEntries(
    [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((shade) => [
      shade,
      cssVar(`--color-${name}-${shade}`),
    ]),
  );

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        slate: scale("slate"),
        indigo: scale("indigo"),
        cyan: scale("cyan"),
        emerald: scale("emerald"),
        rose: scale("rose"),
        amber: scale("amber"),
        fuchsia: scale("fuchsia"),
        sky: scale("sky"),
      },
    },
  },
  plugins: [],
};
