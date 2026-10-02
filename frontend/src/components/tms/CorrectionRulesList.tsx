import { Trash2 } from 'lucide-react';
import { Button } from '../ui/button';
import type { CorrectionRule } from './CorrectionRuleForm';

interface CorrectionRulesListProps {
  rules: Array<CorrectionRule & { index: number }>;
  onDelete: (index: number) => Promise<void>;
  hiddenCount?: number;
}

function formatFactor(v: number | null | undefined): string {
  if (v === null || v === undefined || isNaN(v)) return '?';
  return v.toPrecision(6).replace(/\.?0+$/, '');
}

function formatRuleSummary(rule: CorrectionRule): string {
  const sensorId = rule.sensor_id || '*';
  const correctionType = rule.correction_type || '?';

  let factors = `a=${formatFactor(rule.factor_a)}`;
  const b = formatFactor(rule.factor_b);
  if (b !== '?') {
    factors += `, b=${b}`;
  }

  let window = '';
  if (rule.valid_from || rule.valid_to) {
    const from = rule.valid_from || '...';
    const to = rule.valid_to || '...';
    window = ` - ${from} → ${to}`;
  }

  let notes = '';
  if (rule.notes) {
    notes = ` - _${rule.notes}_`;
  }

  return `\`${sensorId}\` - ${correctionType} (${factors})${window}${notes}`;
}

export function CorrectionRulesList({
  rules,
  onDelete,
  hiddenCount = 0,
}: CorrectionRulesListProps) {
  if (rules.length === 0 && hiddenCount === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No correction rules yet - add one above, or upload a file.
      </p>
    );
  }

  if (rules.length === 0 && hiddenCount > 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No correction rules match the currently loaded sensors.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">{rules.length} rule(s)</p>
      {rules.map((rule) => (
        <div key={rule.index} className="flex items-start gap-2">
          <div className="flex-1 text-sm">
            <span dangerouslySetInnerHTML={{ __html: formatRuleSummary(rule).replace(/`([^`]+)`/g, '<code class="bg-muted px-1 rounded text-xs">$1</code>').replace(/_([^_]+)_/g, '<em>$1</em>') }} />
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(rule.index)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}
      {hiddenCount > 0 && (
        <p className="text-xs text-muted-foreground">
          {hiddenCount} rule(s) hidden - sensor_id/group not present in the currently loaded data.
        </p>
      )}
    </div>
  );
}
