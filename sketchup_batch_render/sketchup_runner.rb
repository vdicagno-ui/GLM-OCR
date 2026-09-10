# encoding: UTF-8
#
# sketchup_runner.rb  --  SketchUp 2017 batch render extension
#
# Questo file viene installato automaticamente dalla GUI dentro la cartella
# Plugins di SketchUp 2017:
#   %APPDATA%\SketchUp\SketchUp 2017\SketchUp\Plugins\skp_batch_render.rb
#
# All'avvio di SketchUp controlla se esiste un "job file"
#   %TEMP%\skp_batch_job.json
# creato dalla GUI. Se esiste:
#   1. apre il file .skp indicato
#   2. per ogni posizione applica camera + luci/ombre
#   3. salva una foto .bmp per ogni posizione nella cartella di output
#   4. scrive un file di stato %TEMP%\skp_batch_status.json
#
# Non salva mai il modello .skp: le modifiche (camera/ombre) restano in memoria
# e la GUI termina il processo di SketchUp senza salvare.

require 'json'
require 'time'
require 'tmpdir'
require 'fileutils'

module SkpBatchRender
  # --- percorsi condivisi con la GUI (convenzione fissa su %TEMP%) -----------
  def self.temp_dir
    ENV['TEMP'] || ENV['TMP'] || Dir.tmpdir
  end

  JOB_FILE    = File.join(temp_dir, 'skp_batch_job.json')
  STATUS_FILE = File.join(temp_dir, 'skp_batch_status.json')
  LOG_FILE    = File.join(temp_dir, 'skp_batch_log.txt')

  @done = false

  def self.log(msg)
    line = "[#{Time.now.strftime('%Y-%m-%d %H:%M:%S')}] #{msg}"
    begin
      File.open(LOG_FILE, 'a') { |f| f.puts(line) }
    rescue StandardError
    end
    puts line
  end

  def self.write_status(status, message, outputs = [])
    data = {
      'status'  => status,
      'message' => message,
      'outputs' => outputs,
      'time'    => Time.now.strftime('%Y-%m-%d %H:%M:%S')
    }
    File.open(STATUS_FILE, 'w') { |f| f.write(JSON.pretty_generate(data)) }
  rescue StandardError => e
    log("Impossibile scrivere lo stato: #{e.message}")
  end

  # --- conversione unita' di misura -> pollici (unita' interna di SketchUp) ---
  UNIT_TO_INCH = {
    'inch' => 1.0, 'in' => 1.0, 'pollici' => 1.0,
    'ft'   => 12.0, 'feet' => 12.0, 'piedi' => 12.0,
    'mm'   => 1.0 / 25.4,
    'cm'   => 1.0 / 2.54,
    'm'    => 39.37007874015748,
    'metri' => 39.37007874015748
  }.freeze

  def self.unit_factor(units)
    return 1.0 if units.nil?
    UNIT_TO_INCH[units.to_s.strip.downcase] || 1.0
  end

  # Deduce automaticamente il fattore di scala confrontando la dimensione reale
  # del modello (diagonale del bounding box, in pollici) con la distanza
  # camera-target letta dal JSON. Sceglie l'unita' che inquadra il modello.
  def self.detect_unit_factor(positions, model)
    bb = model.bounds
    return 1.0 if bb.nil? || bb.empty?
    s = bb.diagonal.to_f # dimensione modello in pollici
    return 1.0 if s <= 0.0

    positions.each do |pos|
      cam = pos['camera']
      next unless cam && cam['eye'] && cam['target']
      e = cam['eye']; t = cam['target']
      d = Math.sqrt((e[0].to_f - t[0].to_f)**2 +
                    (e[1].to_f - t[1].to_f)**2 +
                    (e[2].to_f - t[2].to_f)**2)
      next if d <= 1e-9

      target_ratio = 1.6 # distanza camera ~ 1.6x la dimensione (fov ~35 gradi)
      candidates = {
        'inch' => 1.0,
        'mm'   => 1.0 / 25.4,
        'cm'   => 1.0 / 2.54,
        'm'    => 39.37007874015748,
        'ft'   => 12.0
      }
      best_name = 'inch'; best_factor = 1.0; best_err = nil
      candidates.each do |name, f|
        ratio = (f * d) / s
        next if ratio <= 0.0
        err = (Math.log(ratio) - Math.log(target_ratio)).abs
        if best_err.nil? || err < best_err
          best_err = err; best_name = name; best_factor = f
        end
      end
      log("Auto-unita': diagonale modello=#{s.round(2)} in, distanza camera raw=#{d.round(4)} -> unita'='#{best_name}' (fattore #{best_factor.round(6)})")
      return best_factor
    end
    1.0
  end

  def self.point(arr, f)
    Geom::Point3d.new(arr[0].to_f * f, arr[1].to_f * f, arr[2].to_f * f)
  end

  def self.vector(arr)
    Geom::Vector3d.new(arr[0].to_f, arr[1].to_f, arr[2].to_f)
  end

  def self.truthy(v)
    v ? true : false
  end

  # --- applica la camera ------------------------------------------------------
  # default_factor: fattore di scala gia' risolto (auto o unita' scelta).
  def self.apply_camera(view, cam, default_factor)
    return if cam.nil?
    f = cam['units'] ? unit_factor(cam['units']) : default_factor

    eye    = point(cam['eye'], f)
    target = point(cam['target'], f)
    up     = cam['up'] ? vector(cam['up']) : Z_AXIS

    camera = Sketchup::Camera.new(eye, target, up)

    persp = cam.key?('perspective') ? cam['perspective'] : true
    camera.perspective = persp ? true : false

    if persp && cam['fov']
      camera.fov = cam['fov'].to_f
    elsif !persp && cam['height']
      # vista parallela: "height" e' l'altezza dell'inquadratura in unita' modello
      camera.height = cam['height'].to_f * f
    end

    # image_width proviene dal dump nativo di SketchUp (in pollici); 0 = non impostato
    if cam['image_width'] && cam['image_width'].to_f > 0
      begin
        camera.image_width = cam['image_width'].to_f
      rescue StandardError
      end
    end

    view.camera = camera
    log("  camera eye=#{eye.to_a.map { |v| v.round(2) }} " \
        "target=#{target.to_a.map { |v| v.round(2) }} " \
        "fov=#{camera.perspective? ? camera.fov.round(1) : 'parallel'} (fattore #{f.round(6)})")
  end

  # --- applica luci e ombre ---------------------------------------------------
  #
  # Accetta DUE formati (anche mescolati):
  #  1) chiavi native di SketchUp ShadowInfo, cosi' come esportate dall'API:
  #       "DisplayShadows", "UseSunForAllShading", "Light", "Dark",
  #       "TZOffset", "Latitude", "Longitude", "NorthAngle",
  #       "ShadowTime" (intero time_t Unix) ...
  #  2) alias "amichevoli" minuscoli usati nei file di esempio:
  #       "display_shadows", "light", "dark", "north_angle",
  #       "use_sun_for_shading", "date" + "time_of_day", "time" ...
  def self.apply_shadow(shadow, s)
    return if s.nil?

    s.each do |key, value|
      begin
        case key
        # ---- gestioni speciali ----
        when 'ShadowTime', 'time'
          shadow['ShadowTime'] =
            value.is_a?(Numeric) ? Time.at(value.to_i) : Time.parse(value.to_s)
        when 'ShadowTime_time_t'
          shadow['ShadowTime_time_t'] = value.to_i
        when 'ShadowDate'
          next # non e' una chiave scrivibile: ShadowTime contiene gia' la data
        when 'date', 'time_of_day'
          next # gestiti insieme dopo il ciclo
        # ---- alias amichevoli (file di esempio) ----
        when 'display_shadows'      then shadow['DisplayShadows'] = truthy(value)
        when 'light'                then shadow['Light'] = value.to_i
        when 'dark'                 then shadow['Dark'] = value.to_i
        when 'north_angle'          then shadow['NorthAngle'] = value.to_f
        when 'use_sun_for_shading'  then shadow['UseSunForAllShading'] = truthy(value)
        when 'display_on_ground'    then shadow['DisplayOnGroundPlane'] = truthy(value)
        when 'display_on_all_faces' then shadow['DisplayOnAllFaces'] = truthy(value)
        when 'edges_cast_shadows'   then shadow['EdgesCastShadows'] = truthy(value)
        when 'latitude'             then shadow['Latitude'] = value.to_f
        when 'longitude'            then shadow['Longitude'] = value.to_f
        when 'tz_offset'            then shadow['TZOffset'] = value.to_f
        else
          # chiave nativa ShadowInfo: assegnazione diretta
          shadow[key] = value
        end
      rescue StandardError => e
        log("Ombra: chiave '#{key}' ignorata (#{e.message})")
      end
    end

    # supporto "date" + "time_of_day" dei file di esempio
    if s['date']
      begin
        shadow['ShadowTime'] = Time.parse("#{s['date']} #{s['time_of_day'] || '12:00'}")
      rescue StandardError => e
        log("Ombra: data non valida (#{e.message})")
      end
    end
  end

  # --- render di una posizione -----------------------------------------------
  def self.render_position(model, pos, index, outdir, width, height, factor)
    view = model.active_view
    apply_camera(view, pos['camera'], factor)
    apply_shadow(model.shadow_info, pos['shadows'] || pos['shadow'])

    view = model.active_view
    view.refresh if view.respond_to?(:refresh)

    filename = File.join(outdir, format('pos_%02d.bmp', index))
    opts = {
      :filename    => filename,
      :width       => width,
      :height      => height,
      :antialias   => true,
      :compression => 1.0
    }
    ok = view.write_image(opts)
    raise "write_image ha restituito #{ok.inspect} per #{filename}" unless ok
    log("Salvata #{filename}")
    filename
  end

  # --- esecuzione del job -----------------------------------------------------
  def self.run_job
    return if @done
    return unless File.exist?(JOB_FILE)
    @done = true

    log('Trovato job file, avvio elaborazione...')

    # legge e rimuove subito il job file per non rieseguirlo
    raw = File.read(JOB_FILE)
    begin
      File.delete(JOB_FILE)
    rescue StandardError
    end

    job = JSON.parse(raw)
    skp       = job['skp']
    outdir    = job['output_dir']
    positions = job['positions'] || []
    width     = (job['width']  || 1920).to_i
    height    = (job['height'] || 1080).to_i
    units     = job['units']

    raise "File .skp non trovato: #{skp}" unless skp && File.exist?(skp)
    FileUtils.mkdir_p(outdir)

    log("Apro il modello: #{skp}")
    ok = Sketchup.open_file(skp)
    log("open_file ha restituito: #{ok.inspect}")
    model = Sketchup.active_model
    raise 'Nessun modello attivo dopo open_file' unless model

    # diagnostica: dimensione reale del modello caricato
    bb = model.bounds
    if bb.nil? || bb.empty? || bb.diagonal.to_f <= 0.0
      raise "Il modello sembra vuoto o non caricato (nessuna geometria visibile). " \
            "Controlla il percorso del file .skp. File: #{skp}"
    end
    log("Modello caricato: diagonale=#{bb.diagonal.round(2)} in, " \
        "min=#{bb.min.to_a.map { |v| v.round(2) }}, max=#{bb.max.to_a.map { |v| v.round(2) }}")

    # risolve il fattore di scala delle coordinate camera
    if units.nil? || units.to_s.strip.downcase == 'auto'
      factor = detect_unit_factor(positions, model)
    else
      factor = unit_factor(units)
      log("Unita' impostata manualmente: '#{units}' (fattore #{factor.round(6)})")
    end

    outputs = []
    positions.each_with_index do |pos, i|
      log("Posizione #{i + 1}/#{positions.length}")
      outputs << render_position(model, pos, i + 1, outdir, width, height, factor)
    end

    write_status('done', "Renderizzate #{outputs.length} posizioni.", outputs)
    log('Completato con successo.')
  rescue StandardError => e
    msg = "#{e.class}: #{e.message}"
    log("ERRORE: #{msg}")
    log(e.backtrace.join("\n")) if e.backtrace
    write_status('error', msg)
  end

  # --- scheduler: controlla il job file dopo l'avvio di SketchUp --------------
  def self.schedule
    attempts = 0
    timer_id = UI.start_timer(2.0, true) do
      attempts += 1
      if File.exist?(JOB_FILE)
        UI.stop_timer(timer_id)
        run_job
      elsif attempts > 30 # ~60s: nessun job, smette di controllare
        UI.stop_timer(timer_id)
      end
    end
  end

  # avvia lo scheduler quando SketchUp carica il plugin
  unless defined?(@scheduled) && @scheduled
    @scheduled = true
    begin
      schedule
    rescue StandardError => e
      log("Errore avvio scheduler: #{e.message}")
    end
  end
end
