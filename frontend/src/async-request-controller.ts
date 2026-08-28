export type AsyncRequestToken<Context extends object> = Readonly<
  Context & { generation: number }
>;

export class AsyncRequestController<Context extends object> {
  private generation = 0;

  public constructor(
    private readonly contextsMatch: (left: Context, right: Context) => boolean,
  ) {}

  public begin(context: Context): AsyncRequestToken<Context> {
    this.generation += 1;
    return this.capture(context);
  }

  public capture(context: Context): AsyncRequestToken<Context> {
    return Object.freeze({
      ...context,
      generation: this.generation,
    });
  }

  public invalidate(): void {
    this.generation += 1;
  }

  public isCurrent(
    request: AsyncRequestToken<Context>,
    context: Context,
  ): boolean {
    return (
      request.generation === this.generation &&
      this.contextsMatch(request, context)
    );
  }
}
