typedef struct Point { int x; int y; } Point_t;
struct Config { int mode; unsigned int flags; Point_t origin; };

int global_counter = 0;
Point_t global_point = {0, 0};

int add(int a, int b) { return a + b; }
int sub(int a, int b) { return a - b; }
int compute(int x) { return add(x, sub(x, global_counter)); }
int dist(const Point_t *p) { return p->x + p->y; }
