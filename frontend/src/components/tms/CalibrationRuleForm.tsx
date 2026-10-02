import { useState } from 'react';
import { PlusCircle, Zap } from 'lucide-react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';

export interface CalibrationRule {
  sensor_id: string;
  coef_0: number;
  coef_1: number;
  coef_2: number;
  coef_3?: number | null;
  coef_4?: number | null;
  coef_5?: number | null;
  valid_from?: string | null;
  valid_to?: string | null;
  notes?: string | null;
}

interface CalibrationRuleFormProps {
  sensorOptions: string[]; // ["*", "sensor1", "sensor2", "group1", ...]
  onSubmit: (rule: CalibrationRule) => Promise<void>;
}

// TOMST universal calibration coefficients
const TOMST_UNIVERSAL = {
  coef_0: -11.236,
  coef_1: 21.421,
  coef_2: -18.828,
  coef_3: 9.3021,
  coef_4: -2.7615,
  coef_5: 0.50315,
};

export function CalibrationRuleForm({ sensorOptions, onSubmit }: CalibrationRuleFormProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState<CalibrationRule>({
    sensor_id: '*',
    coef_0: 0,
    coef_1: 1,
    coef_2: 0,
    coef_3: null,
    coef_4: null,
    coef_5: null,
    valid_from: null,
    valid_to: null,
    notes: null,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    setSubmitting(true);
    try {
      await onSubmit(formData);
      // Reset form
      setFormData({
        sensor_id: '*',
        coef_0: 0,
        coef_1: 1,
        coef_2: 0,
        coef_3: null,
        coef_4: null,
        coef_5: null,
        valid_from: null,
        valid_to: null,
        notes: null,
      });
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const fillTOMSTUniversal = () => {
    setFormData({
      ...formData,
      ...TOMST_UNIVERSAL,
      notes: 'TOMST universal calibration',
    });
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Add a calibration rule</CardTitle>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={fillTOMSTUniversal}
          >
            <Zap className="h-4 w-4 mr-2" />
            Fill TOMST Universal
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="sensor">Sensor or group</Label>
              <Select
                value={formData.sensor_id}
                onValueChange={(value) => setFormData({ ...formData, sensor_id: value })}
              >
                <SelectTrigger id="sensor">
                  <SelectValue placeholder="*" />
                </SelectTrigger>
                <SelectContent>
                  {sensorOptions.map((opt) => (
                    <SelectItem key={opt} value={opt}>
                      {opt}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                Blank or "*" = every sensor
              </p>
            </div>
          </div>

          {/* Polynomial coefficients */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label htmlFor="coef_0">coef_0</Label>
              <Input
                id="coef_0"
                type="number"
                step="any"
                value={formData.coef_0}
                onChange={(e) =>
                  setFormData({ ...formData, coef_0: parseFloat(e.target.value) })
                }
                required
              />
            </div>

            <div>
              <Label htmlFor="coef_1">coef_1</Label>
              <Input
                id="coef_1"
                type="number"
                step="any"
                value={formData.coef_1}
                onChange={(e) =>
                  setFormData({ ...formData, coef_1: parseFloat(e.target.value) })
                }
                required
              />
            </div>

            <div>
              <Label htmlFor="coef_2">coef_2</Label>
              <Input
                id="coef_2"
                type="number"
                step="any"
                value={formData.coef_2}
                onChange={(e) =>
                  setFormData({ ...formData, coef_2: parseFloat(e.target.value) })
                }
                required
              />
            </div>

            <div>
              <Label htmlFor="coef_3">coef_3</Label>
              <Input
                id="coef_3"
                type="number"
                step="any"
                value={formData.coef_3 ?? ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    coef_3: e.target.value ? parseFloat(e.target.value) : null,
                  })
                }
              />
            </div>

            <div>
              <Label htmlFor="coef_4">coef_4</Label>
              <Input
                id="coef_4"
                type="number"
                step="any"
                value={formData.coef_4 ?? ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    coef_4: e.target.value ? parseFloat(e.target.value) : null,
                  })
                }
              />
            </div>

            <div>
              <Label htmlFor="coef_5">coef_5</Label>
              <Input
                id="coef_5"
                type="number"
                step="any"
                value={formData.coef_5 ?? ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    coef_5: e.target.value ? parseFloat(e.target.value) : null,
                  })
                }
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label htmlFor="valid_from">Valid from</Label>
              <Input
                id="valid_from"
                type="date"
                value={formData.valid_from ?? ''}
                onChange={(e) =>
                  setFormData({ ...formData, valid_from: e.target.value || null })
                }
              />
              <p className="text-xs text-muted-foreground mt-1">Blank = always</p>
            </div>

            <div>
              <Label htmlFor="valid_to">Valid to</Label>
              <Input
                id="valid_to"
                type="date"
                value={formData.valid_to ?? ''}
                onChange={(e) =>
                  setFormData({ ...formData, valid_to: e.target.value || null })
                }
              />
              <p className="text-xs text-muted-foreground mt-1">Blank = always</p>
            </div>

            <div>
              <Label htmlFor="notes">Notes</Label>
              <Input
                id="notes"
                type="text"
                value={formData.notes ?? ''}
                onChange={(e) =>
                  setFormData({ ...formData, notes: e.target.value || null })
                }
              />
            </div>
          </div>

          {error && (
            <div className="text-sm text-destructive">{error}</div>
          )}

          <Button type="submit" disabled={submitting} className="w-full">
            <PlusCircle className="h-4 w-4 mr-2" />
            {submitting ? 'Adding...' : 'Add rule'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
