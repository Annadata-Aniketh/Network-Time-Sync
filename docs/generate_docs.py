"""Draw the implemented topology with current host addresses and link rates."""

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def create_architecture_diagram(out_path=None):
    output = Path(out_path) if out_path else Path(__file__).with_name('architecture_diagram.png')
    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor('#f7f9fa')
    ax.set(xlim=(0, 16), ylim=(0, 9))
    ax.axis('off')
    ink, green, muted = '#14283b', '#087f70', '#40566a'

    def line(points, color=green):
        xs, ys = zip(*points)
        ax.plot(xs, ys, color=color, linewidth=2, zorder=1)

    def box(x, y, width, height, label, dark=False):
        ax.add_patch(FancyBboxPatch((x-width/2, y-height/2), width, height,
                                   boxstyle='round,pad=0.04,rounding_size=0.08',
                                   facecolor=ink if dark else 'white',
                                   edgecolor=ink if dark else '#ccd7df', linewidth=1.3, zorder=2))
        ax.text(x, y, label, ha='center', va='center', fontsize=12,
                color='white' if dark else ink, linespacing=1.5, zorder=3)

    ax.text(.6, 8.55, 'Network time synchronization', fontsize=25, weight='bold', color=ink)
    ax.text(.6, 8.08, 'UDP application and background traffic over an OpenFlow 1.3 diamond topology',
            fontsize=13, color=muted)
    box(8, 7.25, 10, .7, 'OS-Ken controller (c0)  ·  controls s1–s4 over TCP port 6653')

    line([(2.8, 5.4), (3.5, 5.4), (3.5, 4.5), (4.2, 4.5)])
    line([(2.8, 2.9), (3.5, 2.9), (3.5, 4.5)])
    line([(5.8, 4.5), (6.3, 4.5), (6.3, 5.9), (7.1, 5.9)])
    line([(8.9, 5.9), (9.7, 5.9), (9.7, 4.5), (10.2, 4.5)])
    line([(5.8, 4.5), (6.3, 4.5), (6.3, 3.1), (7.1, 3.1)])
    line([(8.9, 3.1), (9.7, 3.1), (9.7, 4.5)])
    line([(11.8, 4.5), (12.5, 4.5), (12.5, 5.4), (13.2, 5.4)])
    line([(12.5, 4.5), (12.5, 2.9), (13.2, 2.9)])

    box(1.5, 5.4, 2.6, 1.8, 'Three clients\nh_client1 · 10.0.0.11\nh_client2 · 10.0.0.12\nh_client3 · 10.0.0.13')
    box(1.5, 2.9, 2.6, 1.3, 'Background sender\nh_load · 10.0.0.20\nUDP 5001')
    box(5, 4.5, 1.6, 1.2, 's1\nClient edge', dark=True)
    box(8, 5.9, 1.8, 1.1, 's2\nPath A', dark=True)
    box(8, 3.1, 1.8, 1.1, 's3\nPath B', dark=True)
    box(11, 4.5, 1.6, 1.2, 's4\nServer edge', dark=True)
    box(14.5, 5.4, 2.6, 1.6, 'Reference server\nh_server · 10.0.0.1\nUDP 12300')
    box(14.5, 2.9, 2.6, 1.3, 'Background sink\nh_sink · 10.0.0.2\nUDP 5001')
    ax.text(8, 6.62, 'Primary core links: 10 Mbps', ha='center', fontsize=12, color=green)
    ax.text(8, 2.31, 'Alternate core links: 50 Mbps', ha='center', fontsize=12, color=green)
    ax.text(8, 1.38, 'Optimized mode: application queues on Path A edge egress; sync traffic reroutes under load.',
            ha='center', fontsize=12, color=ink)
    ax.text(8, .83, 'Core propagation delay: 2 ms per link  |  Access links: 100 Mbps, 1 ms  |  Virtual client clocks only',
            ha='center', fontsize=11, color=muted)
    fig.tight_layout(pad=.5)
    fig.savefig(output, dpi=180, facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f'Generated architecture diagram: {output}')


if __name__ == '__main__':
    create_architecture_diagram()
