import type { AppConfig, UserCase } from "../api/client";

type Props = {
  fields: AppConfig["user_case_fields"];
  userCase: UserCase;
  onChange: (value: UserCase) => void;
  onReset: () => void;
};

export function TopCaseBar({ fields, userCase, onChange, onReset }: Props) {
  if (!fields.length) {
    return <section className="case-bar skeleton">Ladataan kohdeparametreja...</section>;
  }

  return (
    <section className="case-bar" aria-label="Taloyhtiön perustiedot">
      {fields.map((field) => {
        const value = userCase[field.name];
        return (
          <label className="number-field" key={field.name}>
            <span>{field.label}</span>
            <input
              min={0}
              type="number"
              value={Number(value ?? 0)}
              onChange={(event) =>
                onChange({ ...userCase, [field.name]: Number.parseInt(event.target.value || "0", 10) })
              }
            />
          </label>
        );
      })}
      <button className="reset-defaults" type="button" onClick={onReset}>
        Reset defaults
      </button>
    </section>
  );
}
