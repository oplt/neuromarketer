import CheckCircleRounded from '@mui/icons-material/CheckCircleRounded'
import { Box, ButtonBase } from '@mui/material'

export type AnalyzeWizardStep = 'upload' | 'goal' | 'review' | 'results'

type AnalyzeStepperProps = {
  activeStep: AnalyzeWizardStep
  hasStoredAsset: boolean
  hasGoalContext: boolean
  hasResults: boolean
  onStepChange: (step: AnalyzeWizardStep) => void
}

export default function AnalyzeStepper({
  activeStep,
  hasStoredAsset,
  hasGoalContext,
  hasResults,
  onStepChange,
}: AnalyzeStepperProps) {
  const steps: Array<{ id: AnalyzeWizardStep; label: string; isComplete: boolean; isEnabled: boolean }> = [
    { id: 'upload', label: 'Upload', isComplete: hasStoredAsset, isEnabled: true },
    { id: 'goal', label: 'Goal', isComplete: hasGoalContext, isEnabled: hasStoredAsset },
    { id: 'review', label: 'Review & Run', isComplete: false, isEnabled: hasStoredAsset && hasGoalContext },
    { id: 'results', label: 'Results', isComplete: hasResults, isEnabled: hasResults || activeStep === 'results' },
  ]

  return (
    <Box className="analyze-stepper" role="list" aria-label="Analyze workflow steps">
      {steps.map((step, index) => {
        const isActive = activeStep === step.id
        return (
          <ButtonBase
            aria-current={isActive ? 'step' : undefined}
            className={`analyze-stepper__item ${isActive ? 'is-active' : ''} ${step.isComplete ? 'is-complete' : ''}`.trim()}
            disabled={!step.isEnabled}
            key={step.id}
            onClick={() => onStepChange(step.id)}
            role="listitem"
          >
            <span className="analyze-stepper__index">
              {step.isComplete ? <CheckCircleRounded fontSize="small" /> : index + 1}
            </span>
            <span>{step.label}</span>
          </ButtonBase>
        )
      })}
    </Box>
  )
}
