import SendRounded from '@mui/icons-material/SendRounded'
import {
  Alert,
  Box,
  Button,
  Chip,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useMemo, useState } from 'react'

import { apiRequest } from '../../lib/api'
import type { AuthSession } from '../../lib/session'

type CollaborationPanelProps = {
  entityType: 'analysis_job' | 'analysis_comparison'
  entityId: string | null
  session: AuthSession
  title: string
  subtitle: string
  allowTimestampComments?: boolean
}

type WorkspaceMember = {
  id: string
  email: string
  full_name?: string | null
  role: string
}

type CollaborationComment = {
  id: string
  body: string
  timestamp_ms?: number | null
  segment_label?: string | null
  author?: WorkspaceMember | null
  created_at: string
}

type CollaborationReview = {
  id?: string | null
  entity_type: 'analysis_job' | 'analysis_comparison'
  entity_id: string
  status: 'draft' | 'in_review' | 'changes_requested' | 'approved'
  review_summary?: string | null
  created_by?: WorkspaceMember | null
  assignee?: WorkspaceMember | null
  approved_by?: WorkspaceMember | null
  approved_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  comments: CollaborationComment[]
}

function CollaborationPanel({
  entityType,
  entityId,
  session,
  title,
  subtitle,
  allowTimestampComments = false,
}: CollaborationPanelProps) {
  const sessionToken = session.sessionToken
  const [members, setMembers] = useState<WorkspaceMember[]>([])
  const [review, setReview] = useState<CollaborationReview | null>(null)
  const [reviewStatus, setReviewStatus] = useState<'draft' | 'in_review' | 'changes_requested' | 'approved'>('draft')
  const [assigneeUserId, setAssigneeUserId] = useState<string>('')
  const [reviewSummary, setReviewSummary] = useState('')
  const [commentBody, setCommentBody] = useState('')
  const [commentTimestamp, setCommentTimestamp] = useState('')
  const [commentSegmentLabel, setCommentSegmentLabel] = useState('')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isPostingComment, setIsPostingComment] = useState(false)

  const hasDraftChanges = useMemo(() => {
    return (
      reviewStatus !== (review?.status || 'draft') ||
      assigneeUserId !== (review?.assignee?.id || '') ||
      reviewSummary !== (review?.review_summary || '')
    )
  }, [assigneeUserId, review, reviewStatus, reviewSummary])

  useEffect(() => {
    if (!sessionToken || !entityId) {
      setReview(null)
      return
    }

    const loadData = async () => {
      setIsLoading(true)
      try {
        const [membersResponse, reviewResponse] = await Promise.all([
          apiRequest<{ items: WorkspaceMember[] }>('/api/v1/analysis/collaboration/members', { sessionToken }),
          apiRequest<CollaborationReview>(`/api/v1/analysis/collaboration/${entityType}/${entityId}`, { sessionToken }),
        ])
        setMembers(membersResponse.items)
        setReview(reviewResponse)
        setReviewStatus(reviewResponse.status)
        setAssigneeUserId(reviewResponse.assignee?.id || '')
        setReviewSummary(reviewResponse.review_summary || '')
        setErrorMessage(null)
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load collaboration details.')
      } finally {
        setIsLoading(false)
      }
    }

    void loadData()
  }, [entityId, entityType, sessionToken])

  const handleSaveReview = async () => {
    if (!sessionToken || !entityId) {
      return
    }
    setIsSaving(true)
    try {
      const response = await apiRequest<CollaborationReview>(`/api/v1/analysis/collaboration/${entityType}/${entityId}`, {
        method: 'PUT',
        sessionToken,
        body: {
          status: reviewStatus,
          assignee_user_id: assigneeUserId || null,
          review_summary: reviewSummary.trim() || null,
        },
      })
      setReview(response)
      setReviewStatus(response.status)
      setAssigneeUserId(response.assignee?.id || '')
      setReviewSummary(response.review_summary || '')
      setErrorMessage(null)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to save review settings.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleAddComment = async () => {
    if (!sessionToken || !entityId || !commentBody.trim()) {
      return
    }
    setIsPostingComment(true)
    try {
      const response = await apiRequest<CollaborationReview>(`/api/v1/analysis/collaboration/${entityType}/${entityId}/comments`, {
        method: 'POST',
        sessionToken,
        body: {
          body: commentBody.trim(),
          timestamp_ms: allowTimestampComments && commentTimestamp.trim() ? Number(commentTimestamp) : null,
          segment_label: commentSegmentLabel.trim() || null,
        },
      })
      setReview(response)
      setCommentBody('')
      setCommentTimestamp('')
      setCommentSegmentLabel('')
      setErrorMessage(null)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to add the comment.')
    } finally {
      setIsPostingComment(false)
    }
  }

  if (!entityId) {
    return (
      <Paper className="dashboard-card" elevation={0}>
        <Stack spacing={2}>
          <Typography variant="h6">{title}</Typography>
          <Typography color="text.secondary" variant="body2">
            {subtitle}
          </Typography>
          <Typography color="text.secondary" variant="body2">
            Collaboration becomes available once a concrete analysis or comparison is selected.
          </Typography>
        </Stack>
      </Paper>
    )
  }

  return (
    <Paper className="dashboard-card" elevation={0}>
      <Stack spacing={2}>
        <Stack alignItems={{ xs: 'stretch', sm: 'center' }} direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" spacing={1.5}>
          <Box>
            <Typography variant="h6">{title}</Typography>
            <Typography color="text.secondary" variant="body2">
              {subtitle}
            </Typography>
          </Box>
          {review ? (
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
              <Chip label={review.status.replace('_', ' ')} size="small" variant="outlined" />
              {review.assignee ? <Chip label={`Assignee: ${review.assignee.full_name || review.assignee.email}`} size="small" variant="outlined" /> : null}
            </Stack>
          ) : null}
        </Stack>

        {isLoading || isSaving || isPostingComment ? <LinearProgress sx={{ borderRadius: 999, height: 8 }} /> : null}
        {errorMessage ? <Alert severity="warning">{errorMessage}</Alert> : null}

        <Box className="dashboard-grid dashboard-grid--content">
          <Stack spacing={1.5}>
            <TextField
              label="Review status"
              onChange={(event) => setReviewStatus(event.target.value as typeof reviewStatus)}
              select
              value={reviewStatus}
            >
              <MenuItem value="draft">Draft</MenuItem>
              <MenuItem value="in_review">In review</MenuItem>
              <MenuItem value="changes_requested">Changes requested</MenuItem>
              <MenuItem value="approved">Approved</MenuItem>
            </TextField>

            <TextField
              label="Assignee"
              onChange={(event) => setAssigneeUserId(event.target.value)}
              select
              value={assigneeUserId}
            >
              <MenuItem value="">Unassigned</MenuItem>
              {members.map((member) => (
                <MenuItem key={member.id} value={member.id}>
                  {member.full_name || member.email} · {member.role}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              label="Review summary"
              minRows={4}
              multiline
              onChange={(event) => setReviewSummary(event.target.value)}
              value={reviewSummary}
            />

            <Button disabled={!hasDraftChanges || isSaving} onClick={() => void handleSaveReview()} variant="contained">
              Save review settings
            </Button>
          </Stack>

          <Stack spacing={1.5}>
            <Typography variant="subtitle2">Comments</Typography>
            <TextField
              label="Add comment"
              minRows={4}
              multiline
              onChange={(event) => setCommentBody(event.target.value)}
              value={commentBody}
            />
            {allowTimestampComments ? (
              <TextField
                label="Timestamp (ms)"
                onChange={(event) => setCommentTimestamp(event.target.value)}
                type="number"
                value={commentTimestamp}
              />
            ) : null}
            <TextField
              label="Segment label"
              onChange={(event) => setCommentSegmentLabel(event.target.value)}
              value={commentSegmentLabel}
            />
            <Button disabled={!commentBody.trim() || isPostingComment} onClick={() => void handleAddComment()} startIcon={<SendRounded />} variant="outlined">
              Post comment
            </Button>
          </Stack>
        </Box>

        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Author</TableCell>
              <TableCell>Comment</TableCell>
              {allowTimestampComments ? <TableCell>Timestamp</TableCell> : null}
              <TableCell>Created</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(review?.comments || []).map((comment) => (
              <TableRow key={comment.id}>
                <TableCell>{comment.author?.full_name || comment.author?.email || 'Workspace member'}</TableCell>
                <TableCell>
                  <Stack spacing={0.5}>
                    <Typography variant="body2">{comment.body}</Typography>
                    {comment.segment_label ? (
                      <Typography color="text.secondary" variant="caption">
                        {comment.segment_label}
                      </Typography>
                    ) : null}
                  </Stack>
                </TableCell>
                {allowTimestampComments ? <TableCell>{comment.timestamp_ms != null ? `${comment.timestamp_ms} ms` : '—'}</TableCell> : null}
                <TableCell>{formatDateTime(comment.created_at)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        {review && review.comments.length === 0 ? (
          <Typography color="text.secondary" variant="body2">
            No comments yet. Use this panel for timestamp feedback, approval notes, and assignee handoff.
          </Typography>
        ) : null}
      </Stack>
    </Paper>
  )
}

function formatDateTime(value: string) {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString()
}

export default CollaborationPanel
