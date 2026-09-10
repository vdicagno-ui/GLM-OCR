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

  def self.point(arr, f)
    Geom::Point3d.new(arr[0].to_f * f, arr[1].to_f * f, arr[2].to_f * f)
  end

  def self.vector(arr)
    Geom::Vector3d.new(arr[0].to_f, arr[1].to_f, arr[2].to_f)
  end

  # --- applica la camera ------------------------------------------------------
  def self.apply_camera(view, cam, units)
    return if cam.nil?
    f = unit_factor(cam['units'] || units)

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

    view.camera = camera
  end

  # --- applica luci e ombre ---------------------------------------------------
  def self.apply_shadow(shadow, s)
    return if s.nil?

    shadow['DisplayShadows'] = (s.key?('display_shadows') ? s['display_shadows'] : true) ? true : false
    shadow['Light'] = s['light'].to_i if s['light']
    shadow['Dark']  = s['dark'].to_i  if s['dark']
    shadow['NorthAngle'] = s['north_angle'].to_f if s['north_angle']
    shadow['UseSunForAllShading'] = s['use_sun_for_shading'] ? true : false if s.key?('use_sun_for_shading')
    shadow['DisplayOnAllFaces']   = s['display_on_all_faces'] ? true : false if s.key?('display_on_all_faces')
    shadow['DisplayOnGroundPlane'] = s['display_on_ground'] ? true : false if s.key?('display_on_ground')
    shadow['EdgesCastShadows']    = s['edges_cast_shadows'] ? true : false if s.key?('edges_cast_shadows')

    # posizione geografica (facoltativa) -> influenza la direzione del sole
    shadow['Latitude']  = s['latitude'].to_f  if s['latitude']
    shadow['Longitude'] = s['longitude'].to_f if s['longitude']
    shadow['TZOffset']  = s['tz_offset'].to_f  if s['tz_offset']

    t = parse_time(s)
    shadow['ShadowTime'] = t if t
  end

  # accetta:  "time": "2024-06-21T14:30:00"
  #   oppure  "date": "2024-06-21", "time_of_day": "14:30"
  def self.parse_time(s)
    if s['time']
      begin
        return Time.parse(s['time'].to_s)
      rescue StandardError
      end
    end
    if s['date']
      date = s['date'].to_s
      tod  = (s['time_of_day'] || '12:00').to_s
      begin
        return Time.parse("#{date} #{tod}")
      rescue StandardError
      end
    end
    nil
  end

  # --- render di una posizione -----------------------------------------------
  def self.render_position(model, pos, index, outdir, width, height, units)
    view = model.active_view
    apply_camera(view, pos['camera'], units)
    apply_shadow(model.shadow_info, pos['shadow'])

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
    Sketchup.open_file(skp)
    model = Sketchup.active_model
    raise 'Nessun modello attivo dopo open_file' unless model

    outputs = []
    positions.each_with_index do |pos, i|
      log("Posizione #{i + 1}/#{positions.length}")
      outputs << render_position(model, pos, i + 1, outdir, width, height, units)
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
