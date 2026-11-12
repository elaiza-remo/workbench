from django.core.management.base import BaseCommand, CommandError

from core.accounts import resolve_user
from journal.gitsync import GitError, sync_project
from prep.models import Project


class Command(BaseCommand):
    help = (
        "Import git commits into the project journal.\n"
        "  sync_commits                              sync every project with a repo link or folder\n"
        "  sync_commits \"eFit\"                       sync one project\n"
        "  sync_commits \"eFit\" --repo ~/code/efit    set the local repo folder (creates the project if needed)"
    )

    def add_arguments(self, parser):
        parser.add_argument("project", nargs="?", help="Project name (case-insensitive)")
        parser.add_argument("--repo", help="Path to the git repo folder for this project")
        parser.add_argument("--user", help="Whose projects (default: the first superuser)")

    def handle(self, *args, project=None, repo=None, user=None, **options):
        owner = resolve_user(user)
        mine = Project.objects.for_user(owner)
        if repo and not project:
            raise CommandError("Give a project name with --repo, e.g. sync_commits \"eFit\" --repo ~/code/efit")

        if project:
            obj = mine.filter(name__iexact=project).first()
            if obj is None:
                if not repo:
                    raise CommandError(f"No project called “{project}”. Add --repo to create it.")
                obj = Project.objects.create(owner=owner, name=project, repo_path=repo)
                self.stdout.write(f"Created project “{obj.name}”.")
            elif repo:
                obj.repo_path = repo
                obj.save(update_fields=["repo_path"])
            projects = [obj]
        else:
            projects = [p for p in mine if p.repo_path or p.repo_url]
            if not projects:
                raise CommandError("No projects have a repo link or folder yet. Add one in the app, or use --repo.")

        failed = False
        for p in projects:
            try:
                new, total = sync_project(p)
            except GitError as e:
                failed = True
                self.stderr.write(self.style.ERROR(f"{p.name}: {e}"))
                continue
            self.stdout.write(self.style.SUCCESS(f"{p.name}: imported {new} new commit(s) ({total} checked)."))
        if failed:
            raise CommandError("Some projects couldn't be synced.")
